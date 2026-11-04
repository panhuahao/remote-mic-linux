# SPDX-License-Identifier: GPL-3.0-only
import asyncio
import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlparse
import wave
from remote_bridge import credentials
from remote_bridge.youdao import Results,YoudaoSpeech,params,short_request,checked,wav_header,END_MESSAGE

class ProtocolTests(unittest.TestCase):
    def test_signature_uses_v4_spec(self):
        value=params({'youdao_api':'large'}, {'app_id':'test','secret':'secret'},salt='nonce',now=123)
        self.assertEqual(value['sign'],hashlib.sha256(b'testnonce123secret').hexdigest())
        self.assertNotIn('secret',value)
    def test_end_frame_matches_live_service_literal(self):
        self.assertEqual(END_MESSAGE, bytes([123,34,101,110,100,34,58,32,34,116,114,117,101,34,125]))
    def test_partial_updates_replace_and_only_final_is_committed(self):
        results=Results()
        def feed(text,type):results.feed({'result':[{'segId':0,'st':{'sentence':text,'type':type}}]})
        feed('测',1);feed('测试',1);self.assertEqual(results.text(),'测试');self.assertEqual(results.text(True),'')
        feed('测试通过。',0);feed('错误迟到片段',1)
        self.assertEqual(results.text(True),'测试通过。')
    def test_segment_order_is_deterministic(self):
        r=Results()
        for i,s in [(2,'二。'),(1,'一。')]:r.feed({'result':[{'seg_id':i,'st':{'sentence':s,'type':0}}]})
        self.assertEqual(r.text(True),'一。二。')
    def test_realtime_short_word_format(self):
        r=Results('en');r.feed({'result':[{'seg_id':0,'st':[{'ws':[{'w':'Have'},{'w':'fun.'}]}]}]})
        self.assertEqual(r.text(True),'Have fun.')
    def test_complete_rejects_partial_segments(self):
        r=Results();self.assertFalse(r.complete())
        r.feed({'result':[{'seg_id':1,'st':{'sentence':'partial','type':1}}]})
        self.assertFalse(r.complete())
        r.feed({'result':[{'seg_id':1,'st':{'sentence':'final','type':0}}]})
        self.assertTrue(r.complete())
    def test_remote_error_does_not_echo_secret(self):
        with self.assertRaisesRegex(RuntimeError,'202') as exc:checked({'errorCode':'202','msg':'secret signed url'})
        self.assertNotIn('secret',str(exc.exception))
    def test_short_http_signature_and_wav(self):
        class Response(io.BytesIO):pass
        class Opener:
            def open(inner,req,timeout):
                f=parse_qs(req.data.decode());q=f['q'][0];t=q[:10]+str(len(q))+q[-10:]
                self.assertEqual(f['sign'][0],hashlib.sha256(('app'+t+f['salt'][0]+f['curtime'][0]+'secret').encode()).hexdigest())
                with wave.open(io.BytesIO(base64.b64decode(q))) as wav:
                    self.assertEqual((wav.getframerate(),wav.getnchannels(),wav.getsampwidth()),(16000,1,2))
                    self.assertEqual(wav.readframes(2),b'1234')
                return Response(b'{"errorCode":"0","result":["recognized","alternative"]}')
        with patch('remote_bridge.youdao.urllib.request.build_opener',return_value=Opener()):
            self.assertEqual(short_request(b'1234',{}, {'app_id':'app','secret':'secret'}),'recognized')
    def test_credentials_are_private_and_separate(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(credentials,'PATH',Path(directory)/'credentials.json'):
            credentials.save('app','test-secret')
            self.assertEqual(credentials.PATH.stat().st_mode & 0o777,0o600)
            self.assertEqual(credentials.read()['secret'],'test-secret')

class StreamingTests(unittest.IsolatedAsyncioTestCase):
    async def short_stream_session(self,final,code):
        from websockets.asyncio.server import serve
        events=[]
        async def server(ws):
            await ws.send(json.dumps({'action':'started','errorCode':'0'}))
            async for frame in ws:
                if frame==END_MESSAGE:
                    await ws.send(json.dumps({'action':'recognition','errorCode':'0','result':[
                        {'seg_id':1,'st':{'sentence':'固定测试。','type':0 if final else 1,'partial':not final}}]}))
                    await ws.send(json.dumps({'action':'recognition','errorCode':code,'closeCode':'0'}))
                    return
        async with serve(server,'127.0.0.1',0) as endpoint:
            port=endpoint.sockets[0].getsockname()[1]
            with patch('remote_bridge.youdao.credentials.read',return_value={'app_id':'test','secret':'test'}),patch.dict('remote_bridge.youdao.ENDPOINTS',{'realtime_short':f'ws://127.0.0.1:{port}'}):
                speech=YoudaoSpeech({'youdao_api':'realtime_short'},lambda *event:events.append(event));speech.ready=True
                speech.begin();speech.push(b'\x01\x00'*400);speech.end();await speech.worker;await speech.close()
        return events

    async def test_short_stream_final_then_304_normal_close_commits_once(self):
        events=await self.short_stream_session(True,'304')
        self.assertEqual([v['text'] for k,v in events if k=='transcript'],['固定测试。'])
        self.assertFalse(any(k=='asr_status' and '失败' in v for k,v in events))

    async def test_short_stream_timeout_with_only_partial_does_not_commit(self):
        events=await self.short_stream_session(False,'304')
        self.assertFalse(any(k=='transcript' for k,v in events))
        self.assertTrue(any(k=='asr_status' and '304' in v for k,v in events))

    async def test_normal_close_does_not_hide_authentication_error(self):
        events=await self.short_stream_session(True,'202')
        self.assertFalse(any(k=='transcript' for k,v in events))
        self.assertTrue(any(k=='asr_status' and '202' in v for k,v in events))

    async def test_actual_websocket_frames_end_and_single_final_result(self):
        from websockets.asyncio.server import serve
        frames=[];events=[]
        async def server(ws):
            query=parse_qs(urlparse(ws.request.path).query)
            self.assertEqual(query['asrModel'],['multi-lang-stream-fast-v1'])
            await ws.send(json.dumps({'action':'started','errorCode':'0'}))
            async for frame in ws:
                frames.append(frame)
                if frame==END_MESSAGE:
                    for value,type in [('测',1),('测试。',0)]:
                        await ws.send(json.dumps({'errorCode':'0','result':[{'segId':0,'st':{'sentence':value,'type':type}}]}))
                    await ws.send(json.dumps({'errorCode':'0','isEnd':True}));return
        async with serve(server,'127.0.0.1',0) as endpoint:
            port=endpoint.sockets[0].getsockname()[1]
            with patch('remote_bridge.youdao.credentials.read',return_value={'app_id':'test','secret':'test'}),patch.dict('remote_bridge.youdao.ENDPOINTS',{'large':f'ws://127.0.0.1:{port}'}):
                speech=YoudaoSpeech({'youdao_api':'large'},lambda *event:events.append(event));speech.ready=True
                speech.begin();speech.push(b'\x01\x00'*4000);speech.end();await speech.worker
                self.assertEqual(frames[0][:44],wav_header());self.assertEqual(b''.join(frames[:-1])[44:],b'\x01\x00'*4000)
                transcripts=[v['text'] for k,v in events if k=='transcript'];self.assertEqual(transcripts,['测试。'])
                await speech.close()
    async def test_missing_credentials_never_starts_network(self):
        with patch('remote_bridge.youdao.credentials.read',return_value={'app_id':'','secret':''}):
            speech=YoudaoSpeech({},lambda *args:None);await speech.run();speech.begin()
            self.assertIsNone(speech.worker);self.assertFalse(speech.recording);await speech.close()
