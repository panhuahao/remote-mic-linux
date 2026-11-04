#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Desktop regression for provider switching; no Bluetooth, cloud or paste."""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    sys.path.insert(0,str(ROOT))
    with tempfile.TemporaryDirectory(prefix='remote-mic-ui-test-') as tmp:
        os.environ['XDG_CONFIG_HOME']=tmp
        cfg=json.loads((ROOT/'config.example.json').read_text())
        cfg['voice'].update(mode='youdao',youdao_api='realtime_short',auto_insert=False)
        target=Path(tmp)/'ubuntu-remote-bridge/config.json'
        target.parent.mkdir();target.write_text(json.dumps(cfg))
        from remote_bridge.gui import Window
        from gi.repository import Gtk,GLib
        window=Window();window.show_window();checks={}

        def exercise():
            try:
                def transcript(identifier):
                    window.emit('capture',{'id':identifier,'active':True})
                    window.emit('transcript',{'id':identifier,'text':'界面状态验证',
                        'audio_seconds':1,'elapsed':.1})
                    window.poll()
                transcript(1)
                window.emit('asr_status','有道识别完成');window.poll()
                previous=window.generation
                window.backend.set_active_id('local')
                checks['previous_generation_stopped']=window.generation>previous
                checks['old_result_source_retained']='上一段结果 · 有道' in window.result_heading.get_text()
                checks['selection_pending']='尚未应用' in window.source_status.get_text()
                window.messages.put((previous,'asr_status','有道识别完成'));window.poll()
                checks['stale_success_ignored']='有道识别完成' not in window.asr_status.get_text()
                # Simulate applying only this isolated in-memory test configuration.
                window.settings['voice']['mode']='local';window.backend_changed()
                transcript(2)
                checks['local_source_correct']='本机离线' in window.result_heading.get_text() and '有道' not in window.result_heading.get_text()
            except Exception as exc:
                checks['unexpected_error']=type(exc).__name__
            finally:
                window.on_close()
            return False

        GLib.timeout_add(600,exercise)
        Gtk.main()
        print(json.dumps(checks,ensure_ascii=False))
        return 0 if len(checks)==5 and all(value is True for value in checks.values()) else 1

if __name__=='__main__':raise SystemExit(main())
