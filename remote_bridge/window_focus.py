# SPDX-License-Identifier: GPL-3.0-only
"""Read only X11/XWayland active-window IDs; never window content."""
import ctypes
import ctypes.util
import os
import threading

class ActiveWindow:
    def __init__(self):
        self.lock = threading.Lock()
        self.display = None
        if not os.environ.get("DISPLAY"):
            return
        library = ctypes.util.find_library("X11")
        if not library:
            return
        x = self.x = ctypes.CDLL(library)
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]; x.XOpenDisplay.restype = ctypes.c_void_p
        x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]; x.XDefaultRootWindow.restype = ctypes.c_ulong
        x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]; x.XInternAtom.restype = ctypes.c_ulong
        x.XGetWindowProperty.argtypes = [ctypes.c_void_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_long,ctypes.c_long,ctypes.c_int,ctypes.c_ulong,ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.c_void_p)]
        x.XGetWindowProperty.restype = ctypes.c_int
        x.XFree.argtypes = [ctypes.c_void_p]
        x.XGetInputFocus.argtypes = [ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.c_int)]
        x.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.display = x.XOpenDisplay(None)
        if self.display:
            self.root = x.XDefaultRootWindow(self.display)
            self.atom = x.XInternAtom(self.display, b"_NET_ACTIVE_WINDOW", False)

    def current(self):
        with self.lock:
            if not self.display:
                return None
            focus = ctypes.c_ulong(); revert = ctypes.c_int()
            self.x.XGetInputFocus(self.display,ctypes.byref(focus),ctypes.byref(revert))
            if focus.value in (0,1,self.root):
                # _NET_ACTIVE_WINDOW can retain the last X11 client while
                # the compositor focuses a native Wayland application.
                return None
            kind = ctypes.c_ulong(); size = ctypes.c_int()
            count = ctypes.c_ulong(); remaining = ctypes.c_ulong(); data = ctypes.c_void_p()
            status = self.x.XGetWindowProperty(self.display,self.root,self.atom,0,1,False,0,
                ctypes.byref(kind),ctypes.byref(size),ctypes.byref(count),ctypes.byref(remaining),ctypes.byref(data))
            try:
                if status == 0 and size.value == 32 and count.value and data.value:
                    value = ctypes.cast(data,ctypes.POINTER(ctypes.c_ulong))[0]
                    return int(value) or None
            finally:
                if data.value:
                    self.x.XFree(data)
            return None

    def close(self):
        with self.lock:
            if self.display:
                self.x.XCloseDisplay(self.display)
                self.display = None
