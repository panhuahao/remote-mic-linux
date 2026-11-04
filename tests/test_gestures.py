# SPDX-License-Identifier: GPL-3.0-only
import unittest
from remote_bridge.gestures import Gestures

class Timer:
    cancelled = False
    def __init__(self, at, callback): self.at,self.callback=at,callback
    def cancel(self):self.cancelled=True

class GestureTests(unittest.TestCase):
    def setUp(self):
        self.now=0;self.timers=[];self.fired=[]
        self.g=Gestures(self.fired.append,self.later)
    def later(self,delay,callback):
        timer=Timer(self.now+delay,callback);self.timers.append(timer);return timer
    def advance(self,seconds):
        end=self.now+seconds
        while True:
            pending=[t for t in self.timers if not t.cancelled and t.at<=end]
            if not pending:break
            timer=min(pending,key=lambda t:t.at);timer.cancelled=True;self.now=timer.at;timer.callback()
        self.now=end
    def event(self,value):self.g.handle(('remote',1),value,['single'],['double'],['hold'])
    def test_single_waits_double_window(self):
        self.event(1);self.event(0);self.advance(.29);self.assertEqual(self.fired,[])
        self.advance(.02);self.assertEqual(self.fired,[['single']])
    def test_double_does_not_also_fire_single(self):
        self.event(1);self.event(0);self.advance(.15);self.event(1);self.event(0)
        self.advance(1);self.assertEqual(self.fired,[['double']])
    def test_hold_does_not_fire_click_and_repeat(self):
        self.event(1);self.advance(.6);self.event(2);self.event(0);self.advance(1)
        self.assertEqual(self.fired,[['hold']])
    def test_disconnect_cancels_pending_click(self):
        self.event(1);self.event(0);self.g.cancel('remote');self.advance(1);self.assertEqual(self.fired,[])
    def test_disconnect_cancels_pending_hold(self):
        self.event(1);self.g.cancel();self.advance(1);self.assertEqual(self.fired,[])
    def test_optional_gestures_do_not_delay_single(self):
        self.g.handle(('r',1),1,['single']);self.g.handle(('r',1),0,['single'])
        self.assertEqual(self.fired,[['single']])
