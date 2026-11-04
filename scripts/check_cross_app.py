#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Insert a fixed phrase only into an independently created test window."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PHRASE = '跨应用输入验证。'

def target(directory):
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('GdkX11', '3.0')
    from gi.repository import Gtk, GdkX11, GLib
    window = Gtk.Window(title='跨应用输入验证')
    window.set_default_size(500, 150)
    window.set_border_width(20)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    window.add(box)
    box.pack_start(Gtk.Label(label='仅验证固定文本输入，不录音、不联网、不发送消息'), False, False, 0)
    entry = Gtk.Entry()
    entry.get_accessible().set_name('跨应用验证输入框')
    box.pack_start(entry, False, False, 0)
    window.show_all()
    entry.grab_focus()
    xid = window.get_window().get_xid() if isinstance(window.get_display(), GdkX11.X11Display) else None
    if xid:
        window.present_with_time(GdkX11.x11_get_server_time(window.get_window()))
        GLib.timeout_add(900, lambda:(window.present_with_time(
            GdkX11.x11_get_server_time(window.get_window())), False)[1])
    else:
        window.present()
    (directory/'target.json').write_text(json.dumps({'pid':os.getpid(), 'xid':xid}))
    def finish():
        value = entry.get_text()
        (directory/'result.json').write_text(json.dumps({'passed':value == PHRASE, 'characters':len(value)}))
        Gtk.main_quit()
        return False
    window.connect('destroy', lambda *_:Gtk.main_quit())
    GLib.timeout_add(6500, finish)
    Gtk.main()

def check(backend):
    sys.path.insert(0, str(ROOT))
    with tempfile.TemporaryDirectory(prefix='remote-bridge-test-') as tmp:
        directory = Path(tmp)
        # Isolate settings and credentials; no real recognizer is started.
        os.environ['XDG_CONFIG_HOME'] = str(directory/'config')
        os.environ['GDK_BACKEND'] = 'x11'
        from remote_bridge.gui import Window
        from gi.repository import Gtk, GLib
        bridge = Window()
        snapshots = []
        original_snapshot = bridge.focus.snapshot
        def trace_snapshot():
            token = original_snapshot()
            if not snapshots or snapshots[-1] != token:
                snapshots.append(token)
            return token
        bridge.focus.snapshot = trace_snapshot
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--target', tmp],
                                 env={**os.environ, 'GDK_BACKEND':backend})
        result = {'passed':False, 'backend':backend}
        def send():
            try:
                meta = json.loads((directory/'target.json').read_text())
                token = bridge.focus.snapshot()
                owned = token and (
                    token['backend'] == 'atspi' and token['window'][0] == meta['pid'] or
                    token['backend'] == 'x11' and meta['xid'] is not None and token['window'] == meta['xid'])
                if not owned:
                    result['reason'] = 'Test window is not active; no input sent'
                    result['target_metadata'] = meta
                    result['focus_metadata'] = token
                    result['x11_window'] = bridge.focus.active.current()
                    from gi.repository import Atspi
                    node = bridge.focus.source
                    result['focus_ancestry'] = []
                    for _ in range(12):
                        if not node:
                            break
                        states = node.get_state_set()
                        result['focus_ancestry'].append({
                            'pid':node.get_process_id(), 'role':str(node.get_role()),
                            'active':states.contains(Atspi.StateType.ACTIVE),
                            'focused':states.contains(Atspi.StateType.FOCUSED)})
                        node = node.get_parent()
                    return False
                bridge.emit('capture', {'id':1, 'active':True})
                GLib.timeout_add(300, lambda:(bridge.emit('transcript', {
                    'id':1, 'text':PHRASE, 'audio_seconds':1, 'elapsed':.3}), False)[1])
            except Exception as exc:
                result['reason'] = type(exc).__name__
            return False
        def finish():
            if (directory/'result.json').exists():
                result.update(json.loads((directory/'result.json').read_text()))
            result['input_status'] = bridge.input_status.get_text()
            if not result['passed']:
                result['focus_changes'] = snapshots
            bridge.on_close()
            return False
        GLib.timeout_add(1700, send)
        GLib.timeout_add(7500, finish)
        try:
            Gtk.main()
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=3)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result['passed'] else 1

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('x11','wayland'), default='x11')
    parser.add_argument('--target', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.target:
        target(args.target)
        return 0
    return check(args.backend)

if __name__ == '__main__':
    raise SystemExit(main())
