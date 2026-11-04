# SPDX-License-Identifier: GPL-3.0-only
import unittest
from unittest.mock import patch
from remote_bridge.text_input import TextInserter
from test_keyboard import Output

class InputTests(unittest.TestCase):
    def test_changed_focus_cancels_before_key_events(self):
        with patch('remote_bridge.text_input.UInput',Output),patch('remote_bridge.text_input.time.sleep'):
            out=TextInserter();written=[];out._write=lambda data:written.append(data)
            reads=iter([b'previous',b'hello']);out._read=lambda *_:next(reads)
            checks=iter([True,False])
            self.assertFalse(out.insert('hello',['KEY_LEFTCTRL','KEY_V'],lambda:next(checks)))
            self.assertEqual(out.output.events,[]);self.assertEqual(written,[b'hello',b'previous']);out.close()
    def test_paste_has_no_enter_and_restores_plain_text(self):
        with patch('remote_bridge.text_input.UInput',Output),patch('remote_bridge.text_input.time.sleep'):
            out=TextInserter();written=[];out._write=lambda data:written.append(data)
            reads=iter([b'previous',b'hello']);out._read=lambda *_:next(reads)
            self.assertTrue(out.insert('hello',['KEY_LEFTCTRL','KEY_V']))
            from evdev import ecodes
            self.assertNotIn((ecodes.KEY_ENTER,1),out.output.events)
            self.assertEqual(written,[b'hello',b'previous']);out.close()
