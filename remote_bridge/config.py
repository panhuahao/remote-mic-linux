# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ubuntu-remote-bridge" / "config.json"
MODEL_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "ubuntu-remote-bridge" / "sensevoice"

def validate_action(action):
    from .keyboard import codes
    if isinstance(action, dict):
        if not isinstance(action.get("app"), str) or not re.fullmatch(r"[A-Za-z0-9_.@+-]+\.desktop", action["app"]):
            raise ValueError("应用动作必须指向已安装的 .desktop 应用")
    elif isinstance(action, list):
        codes(action)
    else:
        raise ValueError("动作必须是快捷键列表或应用对象")

def validate(config):
    from .keyboard import codes
    address = config.get("address", "")
    if address and not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", address):
        raise ValueError("蓝牙地址格式应为 AA:BB:CC:DD:EE:FF")
    if not isinstance(config.get("mapping"), dict):
        raise ValueError("mapping 必须是按键映射对象")
    for key, value in config["mapping"].items():
        codes([key])
        validate_action(value)
    for key, gestures in config.setdefault("gestures", {}).items():
        codes([key])
        if not isinstance(gestures, dict):
            raise ValueError("手势配置格式错误")
        for kind, action in gestures.items():
            if kind not in ("double", "hold"):
                raise ValueError("未知按键手势")
            validate_action(action)
    voice = config.setdefault("voice", {})
    voice.setdefault("mode", "local")
    voice.setdefault("language", "auto")
    voice.setdefault("model_dir", str(MODEL_DIR))
    voice.setdefault("auto_insert", True)
    voice.setdefault("paste_shortcut", ["KEY_LEFTCTRL", "KEY_V"])
    voice.setdefault("youdao_api", "large")
    voice.setdefault("youdao_language", "zh-CHS")
    voice.setdefault("youdao_model", "multi-lang-stream-fast-v1")
    if voice["mode"] not in ("local", "youdao", "external"):
        raise ValueError("未知语音模式")
    if voice["youdao_api"] not in ("large", "short", "realtime", "realtime_short"):
        raise ValueError("未知有道接口")
    if voice["youdao_model"] not in ("multi-lang-stream-v1", "multi-lang-stream-fast-v1"):
        raise ValueError("未知有道模型")
    if not re.fullmatch(r"[A-Za-z0-9-]{2,20}", voice["youdao_language"]):
        raise ValueError("有道语言代码格式错误")
    if voice["language"] not in ("auto", "zh", "en", "ja", "ko", "yue"):
        raise ValueError("未知识别语言")
    codes(voice["paste_shortcut"])
    codes(config.get("voice_shortcut", []))
    if config.get("voice_shortcut_mode", "hold") not in ("hold", "toggle"):
        raise ValueError("语音快捷键模式应为 hold 或 toggle")
    return config

def read():
    source = CONFIG if CONFIG.exists() else ROOT / "config.example.json"
    return validate(json.loads(source.read_text()))

def save(config):
    validate(config)
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as out:
        json.dump(config, out, ensure_ascii=False, indent=2)
        out.write("\n")
    os.replace(temporary, CONFIG)
