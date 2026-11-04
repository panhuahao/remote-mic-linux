# SPDX-License-Identifier: GPL-3.0-only
import unittest
from types import SimpleNamespace
from remote_bridge.focus import Focus, Atspi

class FocusTests(unittest.TestCase):
    def setUp(self):
        self.focus=Focus.__new__(Focus)
        self.focus.source=None;self.focus.key=None
        self.xid=100
        self.focus.active=SimpleNamespace(current=lambda:self.xid)
        self.focus._active_accessible_window=lambda:None
    def source(self,role,focused=True):
        self.focus.source=SimpleNamespace(get_state_set=lambda:SimpleNamespace(contains=lambda _:focused),get_role=lambda:role)
        self.focus.key=(1,'/field')
    def test_missing_editable_metadata_keeps_active_window_target(self):
        token=self.focus.snapshot()
        self.assertEqual(token['window'],100)
        self.assertTrue(self.focus.valid(token))
    def test_switching_windows_rejects_stale_transcript(self):
        token=self.focus.snapshot();self.xid=200
        self.assertFalse(self.focus.valid(token))
    def test_switching_known_fields_rejects_stale_transcript(self):
        self.source(Atspi.Role.TEXT);token=self.focus.snapshot();self.focus.key=(1,'/other-field')
        self.assertFalse(self.focus.valid(token))
    def test_detected_password_field_is_blocked(self):
        self.source(Atspi.Role.PASSWORD_TEXT)
        self.assertIsNone(self.focus.snapshot())
    def test_stale_password_from_background_does_not_block(self):
        self.source(Atspi.Role.PASSWORD_TEXT,focused=False)
        self.assertIsNotNone(self.focus.snapshot())
    def test_native_wayland_uses_public_window_metadata(self):
        self.xid=None;self.focus._active_accessible_window=lambda:(123,'/window')
        token=self.focus.snapshot()
        self.assertEqual(token['backend'],'atspi');self.assertTrue(self.focus.valid(token))
    def test_wayland_window_wins_over_stale_xwayland_focus(self):
        self.focus._active_accessible_window=lambda:(123,'/native-window')
        token=self.focus.snapshot()
        self.assertEqual(token['backend'],'atspi')
        self.assertEqual(token['window'],(123,'/native-window'))
        self.focus._active_accessible_window=lambda:(456,'/another-native-window')
        self.assertFalse(self.focus.valid(token))
    def test_activation_after_field_focus_preserves_field(self):
        self.source(Atspi.Role.TEXT)
        self.focus.revision=0
        source=self.focus.source
        window=object()
        self.focus.changed(SimpleNamespace(type='window:activate',source=window))
        self.assertIs(self.focus.source,source)
        self.assertEqual(self.focus.key,(1,'/field'))
        self.assertIs(self.focus.window,window)
    def test_no_active_window_fails_closed(self):
        self.xid=None
        self.assertIsNone(self.focus.snapshot())
    def test_focused_controls_window_wins_over_mutter_decoration(self):
        window=SimpleNamespace(path='/app-window',get_process_id=lambda:123,
            get_role=lambda:Atspi.Role.FRAME,
            get_state_set=lambda:SimpleNamespace(contains=lambda s:s==Atspi.StateType.ACTIVE))
        self.focus.source=SimpleNamespace(get_parent=lambda:window,get_role=lambda:Atspi.Role.TEXT,
            get_state_set=lambda:SimpleNamespace(contains=lambda s:s==Atspi.StateType.FOCUSED))
        self.focus.window=SimpleNamespace(path='/mutter-frame',get_process_id=lambda:999,
            get_state_set=lambda:SimpleNamespace(contains=lambda _:True))
        self.assertEqual(Focus._active_accessible_window(self.focus),(123,'/app-window'))
    def test_inactive_parent_does_not_override_active_window(self):
        parent=SimpleNamespace(path='/background',get_process_id=lambda:123,
            get_role=lambda:Atspi.Role.FRAME,get_parent=lambda:None,
            get_state_set=lambda:SimpleNamespace(contains=lambda _:False))
        self.focus.source=SimpleNamespace(get_parent=lambda:parent,get_role=lambda:Atspi.Role.TEXT,
            get_state_set=lambda:SimpleNamespace(contains=lambda s:s==Atspi.StateType.FOCUSED))
        self.focus.window=SimpleNamespace(path='/foreground',get_process_id=lambda:456,
            get_state_set=lambda:SimpleNamespace(contains=lambda _:True))
        self.assertEqual(Focus._active_accessible_window(self.focus),(456,'/foreground'))
