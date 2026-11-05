# SPDX-License-Identifier: GPL-3.0-only
"""Map only evdev devices whose Bluetooth identity matches the selected remote."""
from .i18n import msg, error_message
import asyncio
from collections import Counter
from contextlib import suppress
from evdev import InputDevice, UInput, ecodes, list_devices
from .gestures import Gestures

def codes(names):
    result = []
    for name in names:
        value = ecodes.ecodes.get(name)
        if not name.startswith("KEY_") or not isinstance(value, int) or value < 1 or value > ecodes.KEY_MAX:
            raise ValueError(msg("无效键名：{name}",name=str(name)))
        if value not in result:
            result.append(value)
    return result

class Keys:
    def __init__(self, config, report, device_factory=UInput, notify=lambda kind, value: None):
        self.report = report
        self.notify = notify
        self.mapping = {ecodes.ecodes[key]: value for key, value in config["mapping"].items()}
        self.advanced = {ecodes.ecodes[key]: value for key, value in config.get("gestures", {}).items()}
        self.gestures = Gestures(self.action)
        self.voice = codes(config.get("voice_shortcut", []))
        self.voice_mode = config.get("voice_shortcut_mode", "hold")
        self.output = device_factory({ecodes.EV_KEY: list(range(1, ecodes.KEY_MAX + 1))},
                                     name="Ubuntu Remote Bridge Keyboard", vendor=1, product=1)
        self.held = Counter()
        self.bindings = {}
        self.devices = {}
        self.tasks = {}
        self.voice_active = False

    def press(self, keys):
        for key in keys:
            if self.held[key] == 0:
                self.output.write(ecodes.EV_KEY, key, 1)
            self.held[key] += 1
        self.output.syn()

    def release(self, keys):
        for key in reversed(keys):
            if self.held[key] > 0:
                self.held[key] -= 1
                if self.held[key] == 0:
                    self.output.write(ecodes.EV_KEY, key, 0)
        self.output.syn()

    def tap(self, keys):
        self.press(keys)
        self.release(keys)

    def action(self, action):
        if isinstance(action, dict):
            self.notify("launch", action["app"])
        else:
            self.tap(codes(action))

    def voice_session(self, active):
        if active == self.voice_active:
            return
        self.voice_active = active
        if self.voice_mode == "toggle":
            self.tap(self.voice)
        elif active:
            self.press(self.voice)
        else:
            self.release(self.voice)

    def event(self, path, event):
        if event.type != ecodes.EV_KEY:
            return
        identity = (path, event.code)
        if event.value == 1:
            label = ecodes.KEY.get(event.code, str(event.code))
            self.notify("key", label if isinstance(label, str) else label[0])
        advanced = self.advanced.get(event.code, {})
        single = self.mapping.get(event.code, [ecodes.KEY.get(event.code, "KEY_RESERVED")])
        if advanced:
            self.gestures.handle(identity, event.value, single,
                                 advanced.get("double"), advanced.get("hold"))
            return
        if isinstance(single, dict):
            if event.value == 1:
                self.action(single)
            return
        if event.value == 1:
            if identity in self.bindings:
                return
            target = codes(single) if event.code in self.mapping else [event.code]
            self.bindings[identity] = target
            self.press(target)
            label = ecodes.KEY.get(event.code, str(event.code))
            self.report(msg("按键：{key}",key=str(label)))
        elif event.value == 0:
            self.release(self.bindings.pop(identity, []))
        elif event.value == 2:
            target = self.bindings.get(identity, [])
            if target:
                self.output.write(ecodes.EV_KEY, target[-1], 2)
                self.output.syn()

    async def _read(self, device):
        try:
            device.grab()
            self.report(msg("按键通道已接入：{device}",device=device.name))
            async for event in device.async_read_loop():
                if event.type == ecodes.EV_SYN and event.code == ecodes.SYN_DROPPED:
                    raise OSError(msg("遥控器按键缓冲溢出，正在重新同步"))
                self.event(device.path, event)
        except OSError as exc:
            self.report(msg("按键通道断开或不可用：{error}",error=error_message(exc)))
        finally:
            self.gestures.cancel(device.path)
            for identity in list(self.bindings):
                if identity[0] == device.path:
                    self.release(self.bindings.pop(identity))
            with suppress(OSError):
                device.ungrab()
            device.close()
            self.devices.pop(device.path, None)

    async def monitor(self, address):
        try:
            while True:
                for path in list_devices():
                    if path in self.devices:
                        continue
                    try:
                        device = InputDevice(path)
                        if device.uniq.lower() != address.lower() or device.info.bustype != ecodes.BUS_BLUETOOTH:
                            device.close()
                            continue
                        self.devices[path] = device
                        task = asyncio.create_task(self._read(device))
                        self.tasks[path] = task
                    except OSError:
                        continue
                await asyncio.sleep(2)
        finally:
            tasks = list(self.tasks.values())
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def close(self):
        self.gestures.cancel()
        self.voice_session(False)
        for key, count in self.held.items():
            if count:
                self.output.write(ecodes.EV_KEY, key, 0)
        self.output.syn()
        self.output.close()
