# SPDX-License-Identifier: GPL-3.0-only
"""Wayland clipboard insertion with no Enter/send action."""
import subprocess
import threading
import time
from evdev import UInput, ecodes
from .keyboard import codes

class TextInserter:
    def __init__(self, clipboard=None):
        self.output = UInput({ecodes.EV_KEY: list(range(1, ecodes.KEY_MAX + 1))},
                             name="Ubuntu Remote Dictation", vendor=1, product=2)
        self.lock = threading.Lock()
        self.closed = False
        if clipboard is not None:
            self._read, self._write = clipboard.read, clipboard.write

    @staticmethod
    def _read(mime=None):
        args = ["wl-paste", "--no-newline"]
        if mime:
            args += ["--type", mime]
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2)
        return result.stdout if result.returncode == 0 else None

    @staticmethod
    def _write(data, mime="text/plain;charset=utf-8"):
        subprocess.run(["wl-copy", "--type", mime], input=data,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=True)

    def insert(self, text, shortcut, still_valid=lambda: True):
        with self.lock:
            if self.closed or not still_valid():
                return False
            previous = self._read("text")
            text_bytes = text.encode("utf-8")
            self._write(text_bytes)
            time.sleep(.08)
            if self.closed or not still_valid():
                if previous is not None and self._read("text") == text_bytes:
                    self._write(previous)
                return False
            keys = codes(shortcut)
            try:
                for key in keys:
                    self.output.write(ecodes.EV_KEY, key, 1)
                self.output.syn()
                time.sleep(.035)
            finally:
                for key in reversed(keys):
                    self.output.write(ecodes.EV_KEY, key, 0)
                self.output.syn()
            # Preserve plain-text clipboard when it has not been changed again.
            time.sleep(1)
            if previous is not None and self._read("text") == text_bytes:
                self._write(previous)
            return True

    def close(self):
        with self.lock:
            self.closed = True
            self.output.close()
