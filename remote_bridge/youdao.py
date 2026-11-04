# SPDX-License-Identifier: GPL-3.0-only
"""Youdao public ASR APIs. Cloud mode is always explicitly selected by the user."""
import asyncio
import base64
import hashlib
import io
import json
import struct
import time
import urllib.parse
import urllib.request
import uuid
import wave
from . import credentials

ENDPOINTS = {"large": "wss://openapi.youdao.com/stream-audio/stream-asr",
             "realtime": "wss://openapi.youdao.com/stream_asropenapi",
             "realtime_short": "wss://openapi.youdao.com/stream_shortasropenapi"}
ERRORS = {"108": "应用 ID 无效", "110": "应用未绑定该语音服务",
          "304": "识别会话闲置超时，本次未完成确认，请重新说话",
          "202": "签名校验失败，请检查应用 ID 和密钥", "203": "IP 未在白名单内",
          "206": "系统时间不正确", "401": "账号余额不足", "411": "调用过于频繁",
          "102": "该接口不支持所选语言", "901206": "该模型不支持所选语言",
          "901210": "连接空闲超时，请检查网络后重新按住说话",
          "901204": "识别服务响应超时，请稍后重试"}
# The live service requires this literal, including the space after the colon.
# Compact JSON failed to terminate test sessions: 901210 instead of isEnd=true.
END_MESSAGE = b'{"end": "true"}'

def checked(message):
    code = str(message.get("errorCode", "0"))
    if code != "0" or message.get("action") == "error":
        raise RuntimeError("有道错误 " + code + "：" + ERRORS.get(code, "请在有道控制台检查服务权限和请求状态"))
    return message

def params(settings, cred, salt=None, now=None):
    salt = salt or str(uuid.uuid4())
    now = str(int(time.time()) if now is None else now)
    app = cred["app_id"]
    value = {"appKey": app, "salt": salt, "curtime": now,
             "sign": hashlib.sha256((app+salt+now+cred["secret"]).encode()).hexdigest(),
             "langType": settings.get("youdao_language", "zh-CHS")}
    if settings.get("youdao_api", "large") == "large":
        value.update(asrModel=settings.get("youdao_model", "multi-lang-stream-fast-v1"),
                     partialAsrRequired="true", vadEos="0")
    else:
        if value["langType"] == "auto":
            raise ValueError("普通有道接口需指定语言，例如 zh-CHS 或 en")
        value.update(signType="v4", format="wav", channel="1", version="v1", rate="16000")
    return value

def wav_header(data_size=0xFFFFFFFF):
    # Unknown-length PCM WAV for live streaming; end is signalled explicitly.
    return struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", min(0xFFFFFFFF,data_size+36),
                       b"WAVE", b"fmt ",16,1,1,16000,32000,2,16,b"data",data_size)

class Results:
    def __init__(self, language="zh-CHS"):
        self.parts = {}
        self.language = language

    def feed(self, message):
        checked(message)
        result = message.get("result", [])
        if not isinstance(result, list):
            return
        for part in result:
            if not isinstance(part, dict):
                continue
            seg = part.get("segId", part.get("seg_id", 0))
            statements = part.get("st", {})
            if isinstance(statements, dict):
                statements = [statements]
            for index, st in enumerate(statements):
                sentence = st.get("sentence")
                if sentence is None:
                    words = [x.get("w", "") for x in st.get("ws", [])]
                    sentence = (" " if self.language.startswith("en") else "").join(words)
                final = st.get("type") in (0, "0") or st.get("partial") is False
                if "type" not in st and "partial" not in st:
                    final = True  # short-stream API only documents completed segments
                key = (int(seg), index)
                if self.parts.get(key, ("", False))[1] and not final:
                    continue
                self.parts[key] = (sentence, final)

    def text(self, final_only=False):
        sep = " " if self.language.startswith("en") else ""
        return sep.join(text.strip() for _,(text,final) in sorted(self.parts.items())
                        if text.strip() and (final or not final_only)).strip()

    def complete(self):
        return bool(self.parts) and all(final for _, final in self.parts.values()) and bool(self.text(True))

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def short_request(data, settings, cred):
    content = io.BytesIO()
    with wave.open(content, "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000); out.writeframes(data)
    q = base64.b64encode(content.getvalue()).decode("ascii")
    salt, now = str(uuid.uuid4()), str(int(time.time()))
    truncated = q if len(q) <= 20 else q[:10] + str(len(q)) + q[-10:]
    signed = cred["app_id"]+truncated+salt+now+cred["secret"]
    fields = {"q":q,"appKey":cred["app_id"],"salt":salt,"curtime":now,
              "sign":hashlib.sha256(signed.encode()).hexdigest(),"signType":"v3",
              "langType":settings.get("youdao_language","zh-CHS"),
              "format":"wav","rate":"16000","channel":"1","type":"1"}
    if fields["langType"] == "auto":
        raise ValueError("短语音接口需指定语言，例如 zh-CHS 或 en")
    req = urllib.request.Request("https://openapi.youdao.com/asrapi",
                                 data=urllib.parse.urlencode(fields).encode(), method="POST")
    with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response:
        result = checked(json.loads(response.read(1024*1024)))
    # result is a list of recognition alternatives, not independent sentences.
    values = result.get("result", [])
    return values[0] if values and isinstance(values[0], str) else ""

class YoudaoSpeech:
    MAX_BYTES = 16000*2*60

    def __init__(self, settings, notify):
        self.settings, self.notify = settings, notify
        self.cred = credentials.read()
        self.ready = self.recording = self.closed = False
        self.identifier = 0
        self.epoch = 0
        self.task = self.worker = None
        self.session = None

    async def run(self):
        if not all(self.cred.values()):
            self.notify("asr_status", "请在语音设置填写有道应用 ID 和应用密钥，再保存连接")
            return
        self.ready = True
        self.notify("asr_status", "有道已配置 · 按住说话（联网传音频；权限待首次请求验证）")
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            pass
        finally:
            self.ready = False

    def begin(self):
        if not self.ready or self.closed:
            self.notify("asr_status", "有道识别尚未配置完成")
            return
        if self.worker and not self.worker.done():
            self.notify("asr_status", "上一段仍在识别，请稍后再说话")
            return
        self.identifier += 1
        self.recording = True
        session = {"id":self.identifier,"epoch":self.epoch,"queue":asyncio.Queue(maxsize=302),
                   "pcm":bytearray(),"total":0,"tail":bytearray(),"ended":False,"end_sent":False}
        self.session = session
        self.notify("capture", {"id":self.identifier,"active":True})
        if self.settings.get("youdao_api") != "short":
            self.worker = asyncio.create_task(self._recognize(session))

    def push(self, data):
        if not self.recording:
            return
        s = self.session
        s["total"] += len(data)
        if s["total"] > self.MAX_BYTES:
            self.invalidate()
            self.notify("asr_status", "语音超过 60 秒，已中止本段识别，请分段说话")
            return
        if self.settings.get("youdao_api") == "short":
            s["pcm"].extend(data)
        else:
            s["tail"].extend(data)
            while len(s["tail"]) >= 6400:
                s["queue"].put_nowait(bytes(s["tail"][:6400]))
                del s["tail"][:6400]

    def end(self, discard=False):
        if not self.recording:
            return
        self.recording = False
        s = self.session
        self.notify("capture", {"id":s["id"],"active":False})
        if discard:
            return
        s["ended"] = True
        if self.settings.get("youdao_api") == "short":
            self.worker = asyncio.create_task(self._recognize(s))
        else:
            if s["tail"]:
                s["queue"].put_nowait(bytes(s["tail"]))
                s["tail"].clear()
            s["queue"].put_nowait(None)

    async def _recognize(self, s):
        started = time.monotonic()
        try:
            if self.settings.get("youdao_api") == "short":
                if len(s["pcm"]) < 6400:
                    self.notify("asr_status", "语音太短，请重新说话")
                    return
                self.notify("asr_status", "正在上传到有道识别…")
                text = await asyncio.to_thread(short_request, bytes(s["pcm"]), self.settings, self.cred)
            else:
                text = await self._stream(s)
            if not self.closed and s["epoch"] == self.epoch:
                self.notify("transcript", {"id":s["id"],"text":text,
                            "audio_seconds":s["total"]/32000,"elapsed":time.monotonic()-started})
                self.notify("asr_status", "有道识别完成" if text else "未识别到完整语句，请再试一次")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            if not self.closed and s["epoch"] == self.epoch:
                # Never expose a signed request URL or server-echoed input.
                message = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else type(exc).__name__
                self.notify("asr_status", "有道识别失败：" + message)
        finally:
            s["pcm"].clear(); s["tail"].clear()
            if self.session is s and self.recording:
                self.recording = False
                self.notify("capture", {"id":s["id"],"active":False})

    async def _stream(self, s):
        from websockets.asyncio.client import connect
        from websockets.exceptions import ConnectionClosedOK
        api = self.settings.get("youdao_api", "large")
        url = ENDPOINTS[api] + "?" + urllib.parse.urlencode(params(self.settings,self.cred))
        class DirectConnect(connect):
            def process_redirect(self, exc):
                return exc  # Never send a signed URL to a redirect target.
        result = Results(self.settings.get("youdao_language", "zh-CHS"))
        self.notify("asr_status", "正在连接有道…")
        async with DirectConnect(url, open_timeout=12, close_timeout=2, max_size=1024*1024, proxy=None) as ws:
            first = checked(json.loads(await asyncio.wait_for(ws.recv(),12)))
            if first.get("action") != "started":
                raise RuntimeError("有道未返回启动确认")
            self.notify("asr_status", "有道已连接 · 正在上传遥控器语音")
            async def send():
                first = True
                while True:
                    chunk = await asyncio.wait_for(s["queue"].get(), 15)
                    if chunk is None:
                        await ws.send(END_MESSAGE)
                        s["end_sent"] = True
                        return
                    await ws.send((wav_header() if first else b'') + chunk)
                    first = False
                    await asyncio.sleep(len(chunk)/32000)
            async def receive():
                while True:
                    try:
                        message = json.loads(await asyncio.wait_for(ws.recv(),25))
                    except ConnectionClosedOK:
                        if api != "large" and s["ended"]:
                            return result.text(final_only=True)
                        raise RuntimeError("有道提前断开，未输入不完整结果")
                    # The short-stream service sends a confirmed final segment,
                    # then a closeCode=0 / errorCode=304 completion envelope.
                    # Accept it only after OUR end frame and all-final segments.
                    # A timeout with partial text or an early close is still an error.
                    if (api == 'realtime_short' and str(message.get('closeCode','')) == '0'
                            and str(message.get('errorCode','0')) in ('0','304')
                            and s['ended'] and s['end_sent'] and result.complete()):
                        return result.text(final_only=True)
                    checked(message)
                    result.feed(message)
                    if s["epoch"] == self.epoch:
                        self.notify("partial", result.text())
                    if message.get("isEnd") is True or str(message.get("closeCode", "")) == "0":
                        if not s["ended"]:
                            raise RuntimeError("有道提前结束，请重新说话")
                        return result.text(final_only=True)
            sender = asyncio.create_task(send())
            receiver = asyncio.create_task(receive())
            try:
                async with asyncio.timeout(100):
                    done, _ = await asyncio.wait([sender,receiver], return_when=asyncio.FIRST_COMPLETED)
                    if sender in done:
                        await sender
                        return await receiver
                    text = await receiver
                    if not sender.done():
                        raise RuntimeError("音频尚未发送完毕，有道已结束识别")
                    await sender
                    return text
            finally:
                sender.cancel(); receiver.cancel()
                await asyncio.gather(sender,receiver,return_exceptions=True)

    def invalidate(self):
        self.epoch += 1
        self.end(discard=True)
        if self.worker:
            self.worker.cancel()

    async def close(self):
        self.closed = True
        self.invalidate()
        for task in (self.worker, self.task):
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
