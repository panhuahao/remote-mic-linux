# SPDX-License-Identifier: GPL-3.0-only
"""PipeWire virtual source; no recording files, uploads, or default changes."""
import json
import os
import select
import subprocess
import threading
import time

class VirtualMicrophone:
    NAME = "ubuntu_remote_mic"
    RATE = 16000
    FRAME_BYTES = 640

    def __init__(self, report=lambda message: None):
        self.report = report
        self.buffer = bytearray()
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.process = None
        self.worker = None
        self.dropped_bytes = 0
        self.peak = 0

    def start(self):
        properties = {
            "media.class": "Audio/Source", "node.name": self.NAME,
            "node.description": "Ubuntu Remote Microphone",
            "node.virtual": True, "node.autoconnect": False,
            "node.always-process": True, "priority.session": 0,
        }
        self.process = subprocess.Popen([
            "pw-cat", "--playback", "--raw", "--format", "s16",
            "--rate", str(self.RATE), "--channels", "1",
            "--channel-map", "MONO", "--target", "0",
            "--latency", "20ms", "--properties", json.dumps(properties), "-",
        ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.set_blocking(self.process.stdin.fileno(), False)
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()
        time.sleep(.15)
        if self.process.poll() is not None:
            self.close()
            raise RuntimeError("无法启动 PipeWire 虚拟麦克风；请检查用户音频服务")

    def push(self, data):
        with self.lock:
            self.buffer.extend(data)
            # Bounded 500 ms queue; report real overruns instead of growing latency.
            if len(self.buffer) > 16000:
                discarded = len(self.buffer) - 16000
                self.dropped_bytes += discarded
                del self.buffer[:discarded]

    def clear(self):
        with self.lock:
            self.buffer.clear()

    def _run(self):
        next_at = time.monotonic()
        pending = b""
        try:
            while not self.stopped.is_set():
                if self.process.poll() is not None:
                    raise RuntimeError("虚拟麦克风进程已退出")
                if not pending:
                    with self.lock:
                        pending = bytes(self.buffer[:self.FRAME_BYTES])
                        del self.buffer[:self.FRAME_BYTES]
                    pending = pending.ljust(self.FRAME_BYTES, b"\0")
                if select.select([], [self.process.stdin], [], .05)[1]:
                    count = os.write(self.process.stdin.fileno(), pending)
                    pending = pending[count:]
                    if not pending:
                        next_at += .02
                        now = time.monotonic()
                        if now > next_at + .1:
                            next_at = now
                        self.stopped.wait(max(0, next_at - now))
        except (OSError, RuntimeError) as exc:
            if not self.stopped.is_set():
                self.report(str(exc))

    def close(self):
        self.stopped.set()
        if self.worker:
            self.worker.join(timeout=1)
        if self.process:
            if self.process.stdin:
                self.process.stdin.close()
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1)
        self.clear()
