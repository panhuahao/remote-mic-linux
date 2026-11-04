# SPDX-License-Identifier: GPL-3.0-only
import argparse
import asyncio
import fcntl
import json
import os
from pathlib import Path
import signal

def main():
    parser = argparse.ArgumentParser(description="Remote Mic Linux — 蓝牙遥控器按键映射与语音输入")
    from . import __version__
    parser.add_argument("--version", action="version", version="Remote Mic Linux " + __version__)
    parser.add_argument("--self-test", action="store_true", help="只检查运行依赖，不连接设备、不上传音频")
    parser.add_argument("--install-model", action="store_true", help="下载并校验离线识别模型")
    parser.add_argument("--install-desktop", action="store_true", help="为当前 AppImage 安装应用列表和桌面图标")
    parser.add_argument("--mirror", action="store_true", help="安装模型时使用明确指定的镜像源")
    parser.add_argument("--scan", action="store_true", help="扫描小米遥控器")
    parser.add_argument("--headless", action="store_true", help="命令行运行")
    parser.add_argument("--autostart", action="store_true", help="打开窗口并自动连接")
    args = parser.parse_args()
    if args.install_desktop:
        import subprocess,sys
        from .config import ROOT
        appimage=os.environ.get('APPIMAGE')
        if not appimage:parser.error('--install-desktop 请通过 AppImage 运行；源码安装请运行 install_desktop.py')
        raise SystemExit(subprocess.call([sys.executable,str(ROOT/'install_desktop.py'),'--appimage',appimage]))
    if args.self_test:
        import importlib
        result = {}
        for name in ('gi', 'cairo', 'numpy', 'sherpa_onnx', 'bleak', 'dbus_fast', 'evdev', 'websockets'):
            module = importlib.import_module(name)
            result[name] = str(Path(module.__file__).resolve())
        import gi
        gi.require_version('Gtk', '3.0');gi.require_version('Atspi', '2.0');gi.require_version('AyatanaAppIndicator3','0.1')
        from gi.repository import Gtk, Atspi, AyatanaAppIndicator3
        from .config import ROOT
        assert (ROOT/'assets/remote-mic-linux.png').is_file()
        assert (ROOT/'remote_bridge/theme.css').is_file()
        print(json.dumps({'app':'Remote Mic Linux','version':__version__,'imports':result,'resources':True}, ensure_ascii=False))
        return
    if args.install_model:
        import subprocess, sys
        from .config import ROOT
        raise SystemExit(subprocess.call([sys.executable, str(ROOT/'install_model.py')]+(['--mirror'] if args.mirror else [])))
    if args.scan:
        from .bridge import scan
        print(json.dumps(asyncio.run(scan()), ensure_ascii=False, indent=2))
        return
    from .identity import acquire_lock, prepare
    prepare()
    if not args.headless:
        from .gui import main as gui
        gui(args.autostart)
        return
    lock = acquire_lock()
    if args.headless:
        from .bridge import Bridge
        from .config import read
        async def run():
            def report(kind, value):
                if kind not in ("level", "devices", "address"):
                    print(kind, value, flush=True)
            bridge = Bridge(read(), report)
            task = asyncio.create_task(bridge.run())
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, task.cancel)
            try:
                await task
            except asyncio.CancelledError:
                pass
        asyncio.run(run())

if __name__ == "__main__":
    main()
