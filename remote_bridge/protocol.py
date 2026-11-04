# SPDX-License-Identifier: GPL-3.0-only
# Adapted 2026-11-04 from SayAll contributors' ATVVProtocol.swift and
# XiaomiBluetoothBridge.swift, commit 96b9df005707c1268e47316e1ba46aed0ef42c63.
# Copyright (C) 2026 SayAll contributors; Ubuntu adaptation contributors.
"""ATVV 16 kHz protocol and high-nibble-first IMA ADPCM decoder."""
from dataclasses import dataclass
import struct

SERVICE = "ab5e0001-5a21-4f05-bc7d-af01f617b664"
TX = "ab5e0002-5a21-4f05-bc7d-af01f617b664"
AUDIO = "ab5e0003-5a21-4f05-bc7d-af01f617b664"
CONTROL = "ab5e0004-5a21-4f05-bc7d-af01f617b664"
GET_CAPABILITIES = bytes.fromhex("0a 01 00 00 03 03")
NAMES = {"mi rc", "xiaomi bluetooth remote 2",
         "xiaomi bluetooth remote 2 pro", "小米蓝牙语音遥控器"}

@dataclass(frozen=True)
class Capabilities:
    version: int
    codecs: int
    interaction: int
    frame_size: int

    @classmethod
    def parse(cls, data):
        if len(data) < 7 or data[0] != 0x0b:
            raise ValueError("无效 ATVV 能力响应")
        version = int.from_bytes(data[1:3], "big")
        if version >= 0x100:
            codecs, interaction = data[3:5]
            if codecs == 0 and len(data) >= 9 and data[4] & 3:
                codecs, interaction = data[4], 3
        else:
            if len(data) < 9:
                raise ValueError("旧版 ATVV 能力响应不完整")
            codecs, interaction = data[4], 0
        if not codecs & 2:
            raise ValueError("此版本仅支持遥控器的 16 kHz 编码")
        size = int.from_bytes(data[5:7], "big") or 120
        if size > 4096:
            raise ValueError("ATVV 帧长异常")
        return cls(version, codecs, interaction, size)

    def mic_open(self):
        return bytes([0x0c, 0]) if self.version >= 0x100 else bytes([0x0c, 0, 2])

    def mic_close(self, session_id=0):
        return bytes([0x0d, session_id]) if self.version >= 0x100 else bytes([0x0d])

class Decoder:
    STEPS = (7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,55,60,66,73,80,88,97,107,118,130,143,157,173,190,209,230,253,279,307,337,371,408,449,494,544,598,658,724,796,876,963,1060,1166,1282,1411,1552,1707,1878,2066,2272,2499,2749,3024,3327,3660,4026,4428,4871,5358,5894,6484,7132,7845,8630,9493,10442,11487,12635,13899,15289,16818,18500,20350,22385,24623,27086,29794,32767)
    INDEX = (-1,-1,-1,-1,2,4,6,8)

    def __init__(self):
        self.reset()

    def reset(self, predictor=0, index=0):
        self.predictor = min(32767, max(-32768, predictor))
        self.index = min(88, max(0, index))

    def decode(self, data):
        output = []
        for byte in data:
            for nibble in (byte >> 4, byte & 15):
                step = self.STEPS[self.index]
                diff = (step >> 3) + ((step >> 2) if nibble & 1 else 0)
                diff += (step >> 1) if nibble & 2 else 0
                diff += step if nibble & 4 else 0
                self.predictor += -diff if nibble & 8 else diff
                self.predictor = min(32767, max(-32768, self.predictor))
                self.index = min(88, max(0, self.index + self.INDEX[nibble & 7]))
                output.append(self.predictor)
        return output

class VoiceProtocol:
    """One instance per connection; raw audio never leaves the process here."""
    def __init__(self, emit, session):
        self.emit, self.session = emit, session
        self.decoder = Decoder()
        self.caps = None
        self.active = False
        self.session_id = 0
        self.pending = bytearray()
        self.sync = None
        self.samples = 0

    def start(self):
        if self.active:
            return
        self.active = True
        self.pending.clear()
        self.sync = None
        self.decoder.reset()
        self.samples = 0
        self.session(True)

    def stop(self):
        was_active, self.active = self.active, False
        self.pending.clear()
        self.sync = None
        if was_active:
            self.session(False)

    def control(self, data):
        if not data:
            return None
        opcode = data[0]
        if opcode == 0x0b:
            self.caps = Capabilities.parse(data)
        elif self.caps is None:
            return None
        elif opcode == 8:
            return self.caps.mic_open()
        elif opcode == 4:
            if len(data) >= 3 and data[2] != 2:
                self.stop()
                raise ValueError("遥控器切换到了不支持的音频编码")
            self.session_id = data[3] if len(data) >= 4 else 0
            self.start()
        elif opcode == 0:
            self.stop()
        elif opcode == 0x0a and len(data) >= 7:
            self.sync = (int.from_bytes(data[4:6], "big", signed=True), data[6])
            self.pending.clear()
        return None

    def audio(self, data):
        # Require STREAM_START. Unexpected or post-stop packets cannot reopen mic.
        if not self.active or self.caps is None:
            return
        self.pending.extend(data)
        size = self.caps.frame_size
        while len(self.pending) >= size:
            frame = bytes(self.pending[:size])
            del self.pending[:size]
            if self.sync is not None:
                self.decoder.reset(*self.sync)
                self.sync = None
            pcm = self.decoder.decode(frame)
            smoothed = pcm.copy()
            for i in range(1, len(pcm) - 1):
                smoothed[i] = (pcm[i-1] + 2 * pcm[i] + pcm[i+1]) >> 2
            self.samples += len(pcm)
            self.emit(struct.pack("<%dh" % len(smoothed), *smoothed))
