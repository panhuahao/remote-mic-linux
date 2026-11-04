# SPDX-License-Identifier: GPL-3.0-only
"""One identity for the window, desktop entry, single instance and tray."""
APP_ID = 'io.github.panhuahao.RemoteMicLinux'
APP_NAME = 'Remote Mic Linux'
ICON_NAME = 'remote-mic-linux'
REPOSITORY_URL = 'https://github.com/panhuahao/remote-mic-linux'

def prepare():
    from gi.repository import GLib
    GLib.set_prgname(APP_ID)
    if GLib.get_application_name()!=APP_NAME:GLib.set_application_name(APP_NAME)

def acquire_lock():
    import fcntl
    import os
    from pathlib import Path
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', str(Path.home()/'.cache')))
    runtime.mkdir(parents=True, exist_ok=True)
    lock = open(runtime/'ubuntu-remote-bridge.lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise SystemExit('Remote Mic Linux 已在运行。请从通知栏打开窗口。')
    return lock
