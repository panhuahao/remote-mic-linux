# SPDX-License-Identifier: GPL-3.0-only
"""Bounded local dictation; PCM stays in memory and is never uploaded."""
from .i18n import msg, error_message
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import time
import numpy as np

class Speech:
    MAX_BYTES = 16000 * 2 * 60

    def __init__(self, settings, notify):
        self.settings, self.notify = settings, notify
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-asr")
        self.recognizer = None
        self.ready = False
        self.closed = False
        self.recording = False
        self.overflow = False
        self.buffer = bytearray()
        self.identifier = 0
        self.queue = asyncio.Queue(maxsize=2)
        self.task = None
        self.epoch = 0

    def _load(self):
        import sherpa_onnx
        directory = Path(self.settings["model_dir"]).expanduser()
        if not (directory/"model.int8.onnx").is_file() or not (directory/"tokens.txt").is_file():
            raise RuntimeError(msg("缺少本地语音模型，请在语音设置中安装模型"))
        return sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(directory/"model.int8.onnx"), tokens=str(directory/"tokens.txt"),
            num_threads=2, language=self.settings.get("language", "auto"),
            use_itn=True, provider="cpu")

    async def run(self):
        loop = asyncio.get_running_loop()
        try:
            self.notify("asr_status", "正在加载本地识别模型…")
            self.recognizer = await loop.run_in_executor(self.executor, self._load)
            if self.closed:
                return
            self.ready = True
            self.notify("asr_status", "本地识别已就绪 · 按住说话，松开输入")
            while not self.closed:
                epoch, identifier, data = await self.queue.get()
                started = time.monotonic()
                self.notify("asr_status", "正在识别…")
                try:
                    text = await loop.run_in_executor(self.executor, self._decode, data)
                except Exception as exc:
                    self.notify("asr_status", msg("本次识别失败：{error}",error=error_message(exc)))
                    continue
                if not self.closed and epoch == self.epoch:
                    result = {"id": identifier, "text": text, "audio_seconds": len(data)/32000,
                              "elapsed": time.monotonic() - started}
                    self.notify("transcript", result)
                    self.notify("asr_status", "识别完成" if text else "未识别到清晰语音，请再试一次")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.ready = False
            self.notify("asr_status", msg("识别不可用：{error}",error=error_message(exc)))
        finally:
            self.ready = False

    def _decode(self, data):
        samples = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768
        if len(samples) < 3200 or float(np.sqrt(np.mean(samples*samples))) < .0005:
            return ""
        stream = self.recognizer.create_stream()
        stream.accept_waveform(16000, samples)
        self.recognizer.decode_stream(stream)
        return re.sub(r"<\|[^>]+\|>", "", stream.result.text).strip()

    def begin(self):
        self.buffer.clear()
        self.overflow = False
        self.recording = self.ready and not self.closed
        self.identifier += 1
        if self.recording:
            self.notify("capture", {"id": self.identifier, "active": True})
        else:
            self.notify("asr_status", "识别尚未就绪，本次仅输出麦克风音频")

    def push(self, data):
        if not self.recording:
            return
        if len(self.buffer) + len(data) > self.MAX_BYTES:
            self.overflow = True
            return
        self.buffer.extend(data)

    def end(self, discard=False):
        if self.recording:
            self.recording = False
            self.notify("capture", {"id": self.identifier, "active": False})
            if not discard and not self.overflow and self.buffer:
                try:
                    self.queue.put_nowait((self.epoch, self.identifier, bytes(self.buffer)))
                except asyncio.QueueFull:
                    self.notify("asr_status", "识别队列已满，请等上一段完成后再说话")
            elif self.overflow:
                self.notify("asr_status", "单段语音超过 60 秒，本次未输入，请分段说话")
        self.buffer.clear()

    def invalidate(self):
        self.epoch += 1
        self.end(discard=True)
        while not self.queue.empty():
            self.queue.get_nowait()

    async def close(self):
        self.closed = True
        self.invalidate()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.executor.shutdown(wait=False, cancel_futures=True)
