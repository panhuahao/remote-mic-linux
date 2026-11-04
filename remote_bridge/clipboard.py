# SPDX-License-Identifier: GPL-3.0-only
"""Use the application's X11 clipboard owner, without a focus-stealing popup."""
import threading
from gi.repository import Gtk, Gdk, GLib

class GtkClipboard:
    def __init__(self):
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.closed = False

    def read(self, _mime=None):
        done = threading.Event()
        result = [None]
        def received(_clipboard, text, _data):
            if text is not None:
                result[0] = text.encode("utf-8")
            done.set()
        def request():
            if not self.closed:
                self.clipboard.request_text(received, None)
            else:
                done.set()
            return False
        GLib.idle_add(request)
        done.wait(.7)
        return result[0]

    def write(self, data):
        done = threading.Event()
        errors = []
        def update():
            try:
                if self.closed:
                    raise RuntimeError("程序已停止")
                self.clipboard.set_text(data.decode("utf-8"), -1)
                Gdk.Display.get_default().flush()
            except Exception as exc:
                errors.append(exc)
            finally:
                done.set()
            return False
        GLib.idle_add(update)
        if not done.wait(1.5):
            raise RuntimeError("剪贴板设置超时")
        if errors:
            raise errors[0]
