# SPDX-License-Identifier: GPL-3.0-only
import unittest
from remote_bridge.protocol import Capabilities, Decoder, VoiceProtocol

class ProtocolTests(unittest.TestCase):
    def test_version_one_and_legacy_capabilities(self):
        for packet in ("0b010002030078", "0b0100000200780000", "0b0001000200780000"):
            caps = Capabilities.parse(bytes.fromhex(packet))
            self.assertEqual(caps.frame_size, 120)
            self.assertEqual(caps.codecs & 2, 2)

    def test_bad_or_unsupported_capabilities_fail_closed(self):
        for packet in (b"", b"\x0b", bytes.fromhex("0b010001030078"), bytes.fromhex("0b01000203ffff")):
            with self.assertRaises(ValueError):
                Capabilities.parse(packet)

    def test_microphone_commands_match_protocol(self):
        v1 = Capabilities.parse(bytes.fromhex("0b010002030078"))
        old = Capabilities.parse(bytes.fromhex("0b0001000200780000"))
        self.assertEqual(v1.mic_open(), bytes.fromhex("0c00"))
        self.assertEqual(old.mic_open(), bytes.fromhex("0c0002"))
        self.assertEqual(v1.mic_close(7), bytes.fromhex("0d07"))
        self.assertEqual(old.mic_close(7), bytes.fromhex("0d"))

    def test_reference_vectors_and_nibble_order(self):
        decoder = Decoder()
        self.assertEqual(decoder.decode(b"\x11"), [1, 2])
        decoder.reset()
        self.assertEqual(decoder.decode(b"\x7f"), [11, -19])

    def test_decoder_clamps_and_chunking_preserves_state(self):
        decoder = Decoder()
        decoder.reset(100000, 1000)
        self.assertEqual((decoder.predictor, decoder.index), (32767, 88))
        decoder.reset()
        data = bytes(range(256))
        expected = decoder.decode(data)
        decoder.reset()
        self.assertEqual(decoder.decode(data[:13]) + decoder.decode(data[13:]), expected)
        self.assertTrue(all(-32768 <= value <= 32767 for value in expected))

    def test_session_fragmentation_sync_stop_and_reconnect(self):
        pcm, events = [], []
        voice = VoiceProtocol(pcm.append, events.append)
        voice.audio(b"\x11" * 120)
        self.assertEqual(pcm, [])
        voice.control(bytes.fromhex("0b010002030078"))
        voice.control(bytes.fromhex("04030207"))
        voice.audio(b"\x11" * 49)
        self.assertEqual(pcm, [])
        voice.audio(b"\x11" * 71)
        self.assertEqual(len(pcm[0]), 480)
        self.assertEqual(voice.samples, 240)
        voice.audio(b"\x22" * 9)
        voice.control(bytes.fromhex("0a000000800058"))
        self.assertEqual(len(voice.pending), 0)
        voice.audio(b"\x11" * 120)
        self.assertEqual(voice.samples, 480)
        voice.control(b"\0")
        voice.audio(b"\x11" * 120)
        self.assertEqual(len(pcm), 2)
        self.assertEqual(events, [True, False])
        voice.control(bytes.fromhex("04030208"))
        voice.audio(b"\x11" * 120)
        self.assertEqual(pcm[0], pcm[-1])
        voice.stop()
        voice.stop()
        self.assertEqual(events, [True, False, True, False])

    def test_remote_request_then_stream_start(self):
        voice = VoiceProtocol(lambda _: None, lambda _: None)
        self.assertIsNone(voice.control(b"\x08"))
        voice.control(bytes.fromhex("0b010002030078"))
        self.assertEqual(voice.control(b"\x08"), bytes.fromhex("0c00"))
        self.assertFalse(voice.active)
        voice.control(bytes.fromhex("04030200"))
        self.assertTrue(voice.active)
        with self.assertRaises(ValueError):
            voice.control(bytes.fromhex("04030100"))
        self.assertFalse(voice.active)

if __name__ == "__main__":
    unittest.main()
