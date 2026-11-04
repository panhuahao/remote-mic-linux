# SPDX-License-Identifier: GPL-3.0-only
"""User-facing action catalogue, independent of the GTK editor."""
PRESETS = [
    ("屏蔽此按键", []), ("上", ["KEY_UP"]), ("下", ["KEY_DOWN"]),
    ("左", ["KEY_LEFT"]), ("右", ["KEY_RIGHT"]), ("确认 / Enter", ["KEY_ENTER"]),
    ("退格", ["KEY_BACKSPACE"]), ("退出 / Escape", ["KEY_ESC"]),
    ("复制", ["KEY_LEFTCTRL", "KEY_C"]), ("粘贴", ["KEY_LEFTCTRL", "KEY_V"]),
    ("剪切", ["KEY_LEFTCTRL", "KEY_X"]), ("撤销", ["KEY_LEFTCTRL", "KEY_Z"]),
    ("重做", ["KEY_LEFTCTRL", "KEY_LEFTSHIFT", "KEY_Z"]),
    ("全选", ["KEY_LEFTCTRL", "KEY_A"]), ("保存", ["KEY_LEFTCTRL", "KEY_S"]),
    ("查找", ["KEY_LEFTCTRL", "KEY_F"]), ("下一个控件 / Tab", ["KEY_TAB"]),
    ("切换应用", ["KEY_LEFTALT", "KEY_TAB"]), ("应用概览 / Super", ["KEY_LEFTMETA"]),
    ("显示桌面", ["KEY_LEFTMETA", "KEY_D"]), ("音量增加", ["KEY_VOLUMEUP"]),
    ("音量降低", ["KEY_VOLUMEDOWN"]), ("静音", ["KEY_MUTE"]),
    ("播放 / 暂停", ["KEY_PLAYPAUSE"]), ("下一首", ["KEY_NEXTSONG"]),
    ("上一首", ["KEY_PREVIOUSSONG"]),
]
REMOTE_KEYS = [
    ("KEY_POWER", "电源", "⏻"), ("KEY_TV", "TV / 应用", "TV"),
    ("KEY_UP", "方向上", "↑"), ("KEY_LEFT", "方向左", "←"),
    ("KEY_ENTER", "确认", "OK"), ("KEY_RIGHT", "方向右", "→"),
    ("KEY_DOWN", "方向下", "↓"), ("KEY_BACK", "返回", "↶"),
    ("KEY_HOMEPAGE", "主页", "⌂"), ("KEY_MENU", "菜单", "☰"),
    ("KEY_VOLUMEUP", "音量 +", "+"), ("KEY_VOLUMEDOWN", "音量 −", "−"),
]
ALIASES = {"KEY_BACK": ["KEY_ESC"], "KEY_HOMEPAGE": ["KEY_HOME"]}

def label(action):
    if isinstance(action, dict):
        return "打开应用：" + action.get("name", action.get("app", ""))
    for name, keys in PRESETS:
        if keys == action:
            return name
    modifiers = {"KEY_LEFTCTRL": "Ctrl", "KEY_RIGHTCTRL": "Ctrl",
                 "KEY_LEFTALT": "Alt", "KEY_RIGHTALT": "Alt",
                 "KEY_LEFTSHIFT": "Shift", "KEY_RIGHTSHIFT": "Shift",
                 "KEY_LEFTMETA": "Super", "KEY_RIGHTMETA": "Super"}
    return " + ".join(modifiers.get(key, key.removeprefix("KEY_")) for key in action)
