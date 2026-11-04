# SPDX-License-Identifier: GPL-3.0-only
import asyncio
from contextlib import suppress
import struct
import time
from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from dbus_fast import Message, BusType, MessageType
from dbus_fast.aio import MessageBus
from .protocol import SERVICE, TX, AUDIO, CONTROL, GET_CAPABILITIES, NAMES, VoiceProtocol
from .audio import VirtualMicrophone
from .keyboard import Keys
from .speech import Speech

async def scan(timeout=8):
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    return [dict(address=device.address, name=ad.local_name or device.name or "ATVV Remote")
            for device, ad in devices.values()
            if (ad.local_name or device.name or "").strip().lower() in NAMES
            or SERVICE in [uuid.lower() for uuid in ad.service_uuids]]

async def resolve_device(address):
    # A connected HID remote may no longer advertise. Read BlueZ's public
    # ObjectManager first, then scan only when it has no cached device object.
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        reply = await bus.call(Message(destination="org.bluez", path="/",
                                       interface="org.freedesktop.DBus.ObjectManager",
                                       member="GetManagedObjects"))
        if reply.message_type != MessageType.ERROR:
            for path, interfaces in reply.body[0].items():
                props = {key: value.value for key, value in interfaces.get("org.bluez.Device1", {}).items()}
                if str(props.get("Address", "")).lower() == address.lower():
                    return BLEDevice(props["Address"], props.get("Name", "MI RC"),
                                     {"path": path, "props": props})
    finally:
        bus.disconnect()
    return await BleakScanner.find_device_by_address(address, timeout=12)

class Bridge:
    def __init__(self, config, notify):
        self.config, self.notify = config, notify
        self.stop_event = asyncio.Event()
        self.audio = None
        self.keys = None
        self.last_level = 0
        self.speech = None
        self.discarding = False

    def report(self, message):
        self.notify("log", message)

    async def pause(self, seconds):
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self.stop_event.wait(), seconds)

    def session(self, active):
        if active:
            self.audio.clear()
        if self.speech:
            if active:
                self.speech.begin()
            else:
                self.speech.end(discard=self.discarding)
        if self.keys:
            self.keys.voice_session(active)
        self.notify("voice", active)
        self.report("开始接收遥控器语音" if active else "遥控器语音结束")

    def pcm(self, data):
        self.audio.push(data)
        if self.speech:
            self.speech.push(data)
        if time.monotonic() - self.last_level > .1:
            self.last_level = time.monotonic()
            values = struct.unpack("<%dh" % (len(data)//2), data)
            self.notify("level", max(map(abs, values), default=0) / 32768)

    async def connected(self, address):
        disconnected = asyncio.Event()
        protocol_error = []
        commands = asyncio.Queue()
        voice = VoiceProtocol(self.pcm, self.session)
        self.discarding = False
        keys_task = None
        self.notify("status", "连接遥控器并协商语音…")
        device = await resolve_device(address)
        if device is None:
            raise RuntimeError("未发现遥控器广播；请靠近电脑并按键唤醒，首次使用需进入配对模式")
        client = BleakClient(device, disconnected_callback=lambda _: disconnected.set(), timeout=25, pair=True)
        try:
            await asyncio.wait_for(client.connect(), 30)
            for uuid in (TX, AUDIO, CONTROL):
                if client.services.get_characteristic(uuid) is None:
                    raise RuntimeError("未发现 ATVV 语音通道；请完成系统蓝牙配对后重连")
            model_char = client.services.get_characteristic("00002a24-0000-1000-8000-00805f9b34fb")
            if model_char:
                model = bytes(await client.read_gatt_char(model_char)).decode(errors="replace").strip("\0")
                self.report("遥控器型号：" + model)
            capabilities_ready = asyncio.Event()

            def control(_, data):
                try:
                    response = voice.control(bytes(data))
                    if voice.caps:
                        capabilities_ready.set()
                    if response is not None:
                        commands.put_nowait(response)
                except Exception as exc:
                    protocol_error.append(exc)
                    capabilities_ready.set()
                    disconnected.set()

            def audio(_, data):
                if not disconnected.is_set():
                    voice.audio(bytes(data))

            await client.start_notify(CONTROL, control)
            await client.start_notify(AUDIO, audio)
            tx = client.services.get_characteristic(TX)
            response = "write-without-response" not in tx.properties
            await client.write_gatt_char(tx, GET_CAPABILITIES, response=response)
            await asyncio.wait_for(capabilities_ready.wait(), 8)
            if protocol_error:
                raise protocol_error[0]
            self.report("ATVV 已就绪：16 kHz / 单声道 / 帧长 %d" % voice.caps.frame_size)
            if self.config.get("mapping_enabled", True):
                try:
                    key_config = dict(self.config)
                    if self.speech:
                        key_config["voice_shortcut"] = []
                    self.keys = Keys(key_config, self.report, notify=self.notify)
                    keys_task = asyncio.create_task(self.keys.monitor(address))
                except (OSError, PermissionError) as exc:
                    self.report("按键映射不可用：" + str(exc))
            self.notify("status", "已连接；按住语音键说话")
            self.notify("address", address)
            while not self.stop_event.is_set() and not disconnected.is_set():
                try:
                    command = await asyncio.wait_for(commands.get(), .15)
                    await client.write_gatt_char(tx, command, response=response)
                except asyncio.TimeoutError:
                    pass
            if protocol_error:
                raise protocol_error[0]
        finally:
            self.discarding = True
            if self.speech:
                self.speech.invalidate()
            self.notify("invalidate", None)
            if voice.active and voice.caps and client.is_connected:
                with suppress(Exception):
                    await asyncio.wait_for(client.write_gatt_char(TX, voice.caps.mic_close(voice.session_id)), 2)
            voice.stop()
            self.audio.clear()
            if keys_task:
                keys_task.cancel()
                await asyncio.gather(keys_task, return_exceptions=True)
            if self.keys:
                self.keys.close()
                self.keys = None
            if client.is_connected:
                with suppress(Exception):
                    await asyncio.wait_for(client.disconnect(), 5)

    async def run(self):
        try:
            self.audio = VirtualMicrophone(self.report)
            self.audio.start()
            self.report("虚拟麦克风：Ubuntu Remote Microphone")
            if self.config.get("voice", {}).get("mode", "local") == "local":
                self.speech = Speech(self.config["voice"], self.notify)
                self.speech.task = asyncio.create_task(self.speech.run())
            elif self.config.get("voice", {}).get("mode") == "youdao":
                from .youdao import YoudaoSpeech
                self.speech = YoudaoSpeech(self.config["voice"], self.notify)
                self.speech.task = asyncio.create_task(self.speech.run())
            else:
                self.notify("asr_status", "外部应用模式 · 请在识别应用中选择 Ubuntu Remote Microphone")
            while not self.stop_event.is_set():
                try:
                    address = self.config.get("address")
                    if not address:
                        self.notify("status", "扫描小米遥控器；请进入配对模式…")
                        devices = await scan()
                        self.notify("devices", devices)
                        if len(devices) != 1:
                            self.notify("status", "未发现遥控器，继续扫描…" if not devices else "发现多个遥控器，请选择设备后连接")
                            await self.pause(3)
                            continue
                        address = devices[0]["address"]
                    await self.connected(address)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.report("连接未成功：%s: %s" % (type(exc).__name__, exc))
                    self.notify("status", "等待遥控器；3 秒后重试")
                await self.pause(3)
        finally:
            if self.speech:
                await self.speech.close()
            if self.audio:
                self.audio.close()
            self.notify("status", "已停止")
            self.notify("voice", False)
