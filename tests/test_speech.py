# SPDX-License-Identifier: GPL-3.0-only
import asyncio
import threading
import unittest
from remote_bridge.speech import Speech

class CaptureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events=[];self.s=Speech({},lambda *e:self.events.append(e));self.s.ready=True
    async def asyncTearDown(self):await self.s.close()
    async def test_disconnected_clip_is_not_transcribed(self):
        self.s.begin();self.s.push(b'\x01\x00'*4000);self.s.end(discard=True)
        self.assertTrue(self.s.queue.empty());self.assertFalse(self.s.buffer)
    async def test_overlong_clip_is_rejected(self):
        self.s.MAX_BYTES=4;self.s.begin();self.s.push(b'123456');self.s.end()
        self.assertTrue(self.s.queue.empty());self.assertTrue(any('超过' in str(x) for x in self.events))
    async def test_queue_is_bounded(self):
        for _ in range(3):self.s.begin();self.s.push(b'12');self.s.end()
        self.assertEqual(self.s.queue.qsize(),2)
    async def test_invalidate_clears_queue(self):
        self.s.begin();self.s.push(b'12');self.s.end();self.s.invalidate();self.assertTrue(self.s.queue.empty())
    async def test_inflight_result_is_discarded_on_disconnect(self):
        started=threading.Event();release=threading.Event()
        self.s._load=lambda:object()
        def decode(_):started.set();release.wait(2);return 'stale text'
        self.s._decode=decode;self.s.task=asyncio.create_task(self.s.run())
        while self.s.recognizer is None:await asyncio.sleep(.01)
        self.s.begin();self.s.push(b'12');self.s.end()
        while not started.is_set():await asyncio.sleep(.01)
        self.s.invalidate();release.set();await asyncio.sleep(.1)
        self.assertFalse(any(k=='transcript' for k,v in self.events))
    async def test_one_decode_failure_does_not_disable_engine(self):
        self.s._load=lambda:object();calls=[]
        def decode(_):
            calls.append(1)
            if len(calls)==1:raise RuntimeError('bad clip')
            return 'ok'
        self.s._decode=decode;self.s.task=asyncio.create_task(self.s.run())
        while self.s.recognizer is None:await asyncio.sleep(.01)
        for _ in range(2):self.s.begin();self.s.push(b'12');self.s.end()
        await asyncio.sleep(.1)
        self.assertTrue(any(k=='transcript' and v['text']=='ok' for k,v in self.events))
