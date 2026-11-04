# SPDX-License-Identifier: GPL-3.0-only
"""Observe public accessibility focus, without reading application text."""
import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi
from .window_focus import ActiveWindow

class Focus:
    def __init__(self):
        self.revision = 0
        self.key = None
        self.editable = False
        self.source = None
        self.window = None
        self.password = False
        self.active = ActiveWindow()
        self.listener = Atspi.EventListener.new(self.changed)
        self.events = ("object:state-changed:focused", "window:activate", "window:deactivate")
        for event in self.events:
            self.listener.register(event)

    def changed(self, event, *_):
        try:
            if event.type == "window:activate":
                self.revision += 1
                self.window = event.source
                # A window activation can follow its child's focus event.
                # Do not discard the already focused child in that window.
                return
            if event.type == "window:deactivate":
                self.revision += 1
                return
            source = event.source
            key = (source.get_process_id(), source.path)
            if not event.detail1:
                if key == self.key:
                    self.revision += 1
                    self.editable = False
                return
            if key != self.key or not self.editable:
                self.revision += 1
            self.key = key
            self.source = source
            state = source.get_state_set()
            role = source.get_role()
            self.password = role == Atspi.Role.PASSWORD_TEXT
            self.editable = role != Atspi.Role.PASSWORD_TEXT and (
                state.contains(Atspi.StateType.EDITABLE) or role == Atspi.Role.TERMINAL)
        except Exception:
            self.revision += 1
            self.editable = False

    def snapshot(self):
        field = None
        password = False
        try:
            if self.source and self.source.get_state_set().contains(Atspi.StateType.FOCUSED):
                field = self.key
                password = self.source.get_role() == Atspi.Role.PASSWORD_TEXT
        except Exception:
            pass
        if password:
            return None
        # Prefer compositor-visible accessibility state. XWayland may retain
        # BOTH its last active-window ID and X input focus under native Wayland.
        window = self._active_accessible_window()
        if window:
            return {"backend":"atspi", "window":window, "field":field}
        xid = self.active.current()
        if xid:
            return {"backend":"x11", "window":xid, "field":field}
        return None

    def _active_accessible_window(self):
        # Mutter's X11 frame decorations can report ACTIVE too. Prefer the
        # actual active window containing the focused application control.
        try:
            node = self.source
            if node and node.get_state_set().contains(Atspi.StateType.FOCUSED):
                for _ in range(32):
                    if node.get_role() in (Atspi.Role.FRAME, Atspi.Role.DIALOG, Atspi.Role.WINDOW) and node.get_state_set().contains(Atspi.StateType.ACTIVE):
                        self.window = node
                        return (node.get_process_id(), node.path)
                    node = node.get_parent()
                    if not node:
                        break
        except Exception:
            pass
        try:
            if self.window and self.window.get_state_set().contains(Atspi.StateType.ACTIVE):
                return (self.window.get_process_id(),self.window.path)
            desktop = Atspi.get_desktop(0)
            for i in range(desktop.get_child_count()):
                app = desktop.get_child_at_index(i)
                for j in range(app.get_child_count()):
                    win = app.get_child_at_index(j)
                    if win.get_state_set().contains(Atspi.StateType.ACTIVE):
                        self.window = win
                        return (win.get_process_id(),win.path)
        except Exception:
            pass
        return None

    def valid(self, token):
        if token is None:
            return False
        current = self.snapshot()
        if current is None or current["backend"] != token["backend"] or current["window"] != token["window"]:
            return False
        # When both applications expose field identity, also check the field.
        return not (token["field"] and current["field"] and token["field"] != current["field"])

    def close(self):
        for event in self.events:
            self.listener.deregister(event)
        self.active.close()
