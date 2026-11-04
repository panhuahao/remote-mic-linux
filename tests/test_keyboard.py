# SPDX-License-Identifier: GPL-3.0-only
import unittest
from types import SimpleNamespace
from evdev import ecodes as e
from remote_bridge.keyboard import Keys, codes
from remote_bridge.config import validate

class Output:
    def __init__(self, *args, **kwargs):
        self.events = []
        self.closed = False
    def write(self, event_type, key, value):
        self.events.append((key, value))
    def syn(self):
        pass
    def close(self):
        self.closed = True

class KeyboardTests(unittest.TestCase):
    def setUp(self):
        self.keys = Keys({"mapping": {"KEY_TV": ["KEY_LEFTALT", "KEY_TAB"], "KEY_F5": []},
                          "voice_shortcut": ["KEY_LEFTALT", "KEY_SPACE"]}, lambda _: None, Output)
    def event(self, code, value, path="remote"):
        self.keys.event(path, SimpleNamespace(type=e.EV_KEY, code=code, value=value))

    def test_chord_repeat_and_release(self):
        self.event(e.KEY_TV, 1)
        self.event(e.KEY_TV, 2)
        self.event(e.KEY_TV, 0)
        self.assertEqual(self.keys.output.events, [(e.KEY_LEFTALT,1),(e.KEY_TAB,1),
                                                  (e.KEY_TAB,2),(e.KEY_TAB,0),(e.KEY_LEFTALT,0)])

    def test_voice_f5_is_not_injected(self):
        self.event(e.KEY_F5, 1)
        self.event(e.KEY_F5, 0)
        self.assertEqual(self.keys.output.events, [])

    def test_shared_modifiers_not_released_early(self):
        self.event(e.KEY_TV, 1)
        self.keys.voice_session(True)
        self.event(e.KEY_TV, 0)
        self.assertNotIn((e.KEY_LEFTALT,0), self.keys.output.events)
        self.keys.voice_session(False)
        self.assertEqual(self.keys.output.events.count((e.KEY_LEFTALT,0)), 1)

    def test_shutdown_releases_all_keys(self):
        self.event(e.KEY_TV, 1)
        self.keys.voice_session(True)
        self.keys.close()
        self.assertIn((e.KEY_SPACE,0), self.keys.output.events)
        self.assertIn((e.KEY_TAB,0), self.keys.output.events)
        self.assertIn((e.KEY_LEFTALT,0), self.keys.output.events)
        self.assertTrue(self.keys.output.closed)

    def test_repeated_keydown_does_not_stick(self):
        self.event(e.KEY_TV, 1)
        self.event(e.KEY_TV, 1)
        self.event(e.KEY_TV, 0)
        self.assertEqual(self.keys.held[e.KEY_LEFTALT], 0)

    def test_bad_config_rejected(self):
        for invalid in (["KEY_DOES_NOT_EXIST"], ["BTN_LEFT"]):
            with self.assertRaises(ValueError):
                codes(invalid)
        with self.assertRaises(ValueError):
            validate({"address": "invalid", "mapping": {}})

if __name__ == "__main__":
    unittest.main()
