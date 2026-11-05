#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exercise live UI translation with isolated settings and synthetic events.

Uses no Bluetooth, recording, cloud service, clipboard writing or key injection.
Run in a graphical session: .venv/bin/python scripts/check_i18n_ui.py
"""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0,str(ROOT))
    with tempfile.TemporaryDirectory(prefix='remote-mic-i18n-test-') as temporary:
        os.environ['XDG_CONFIG_HOME']=temporary
        settings=json.loads((ROOT/'config.example.json').read_text())
        settings['voice'].update(mode='youdao',youdao_api='realtime_short',language='ja',auto_insert=False)
        folder=Path(temporary)/'ubuntu-remote-bridge';folder.mkdir()
        config_path=folder/'config.json';config_path.write_text(json.dumps(settings))
        secret_path=folder/'youdao-credentials.json';secret_path.write_text('{"app_id":"test-id","secret":"test-secret"}')
        from remote_bridge.i18n import save_locale,load_locale,msg
        save_locale('en')
        from remote_bridge.gui import Window
        from remote_bridge.action_editor import ActionDialog
        from gi.repository import Gtk,GLib
        window=Window();window.show_window();checks={}

        def exercise():
            dialog=None
            try:
                checks['startup_saved_locale']=window.page_title.get_text()=='Button mapping'
                window.navigate(2)
                window.address.set_text('AA:BB:CC:DD:EE:FF')
                window.cloud_language.get_child().set_text('en')
                window.model_path.set_text('/tmp/unsaved-model-path')
                window.shortcut.set_text('KEY_F9')
                window.settings['mapping']['KEY_UP']=['KEY_LEFTCTRL','KEY_A'];window.refresh_mapping()
                window.test_entry.get_buffer().set_text('Preserve my test text 中文')
                window.emit('capture',{'id':42,'active':True})
                window.emit('partial','保留这段预览 {text}')
                window.emit('voice',True)
                window.emit('status',msg('已连接；按住语音键说话'))
                window.emit('asr_status',msg('有道已连接 · 正在上传遥控器语音'))
                window.emit('log',msg('遥控器型号：{model}',model='Test Remote'))
                window.poll()
                generation=window.generation;focus=dict(window.capture_focus)
                source=dict(window.capture_sources);selected=window.selected_voice_choice
                config_before=config_path.read_bytes();secret_before=secret_path.read_bytes()
                state_before=copy.deepcopy(window.settings);bridge=object();window.bridge=bridge
                selection_events=[]
                for widget in (window.backend,window.cloud_api,window.cloud_model,window.language):
                    widget.connect('changed',lambda *_:selection_events.append(True))
                # A live action editor retains custom text/choice while both
                # its title, buttons and preset labels are translated.
                dialog=ActionDialog(window,msg('{key} · {gesture}',key=msg('方向上'),gesture=msg('双击')),
                                    ['KEY_LEFTCTRL','KEY_J'],True)
                dialog.choice.set_active_id('custom');dialog.entry.set_text('Ctrl+Alt+Space')
                window.set_ui_language('zh_CN')
                checks['chinese_live_labels']=(window.page_title.get_text()=='测试与结果' and
                    window.voice.get_text()=='正在接收语音… 松开结束' and dialog.get_title()=='方向上 · 双击')
                window.language_button.clicked()
                checks['english_button_and_labels']=(window.i18n.locale=='en' and window.page_title.get_text()=='Test & Results' and
                    window.voice.get_text()=='Receiving speech… Release to finish' and dialog.get_title()=='Up · Double press')
                checks['recording_connection_preserved']=(window.generation==generation and window.bridge is bridge and
                    window.capture_focus==focus and window.capture_sources==source and window.tray.recording)
                checks['selection_signals_unchanged']=not selection_events
                checks['editing_preserved']=(window.address.get_text()=='AA:BB:CC:DD:EE:FF' and
                    window.cloud_language.get_child().get_text()=='en' and window.model_path.get_text()=='/tmp/unsaved-model-path' and
                    window.shortcut.get_text()=='KEY_F9' and dialog.entry.get_text()=='Ctrl+Alt+Space' and
                    dialog.choice.get_active_id()=='custom' and window.selected_voice_choice==selected and
                    window.settings==state_before and window.notebook.get_current_page()==2)
                checks['preview_preserved']=window.result_text()=='保留这段预览 {text}'
                checks['mapping_preset_translated']=window.mapping_buttons[('KEY_UP','single')].get_label()=='Select all'
                checks['config_and_credentials_untouched']=(config_path.read_bytes()==config_before and secret_path.read_bytes()==secret_before)
                checks['locale_saved_separately']=load_locale()=='en'
                checks['source_and_logs_translated']=('Youdao' in window.source_status.get_text() and
                    'Remote model: Test Remote' in window.logs.get_buffer().get_text(*window.logs.get_buffer().get_bounds(),True))
                checks['badge_still_connected']=window.connection_badge.get_text()=='●  Connected'
                if window.tray.indicator:
                    checks['tray_live_translated']=(window.tray.status_item.get_label()=='Receiving speech · Release to finish' and
                        window.tray.menu.get_children()[2].get_label()=='Open Remote Mic Linux')
                # Late worker errors use the active display language and keep
                # their canonical classification and safe-preview behavior.
                window.emit('asr_status',msg('有道识别失败：{error}',error=msg('应用 ID 无效')));window.poll()
                checks['late_error_translated_and_classified']=(window.asr_status.get_text()=='Youdao recognition failed: Invalid App ID' and
                    window.result_heading.get_text().startswith('Unconfirmed preview · Youdao'))
                window.set_ui_language('zh_CN')
                checks['dynamic_error_retranslated']=window.asr_status.get_text()=='有道识别失败：应用 ID 无效'
            except Exception as error:
                checks['unexpected_error']=f'{type(error).__name__}: {error}'
            finally:
                if dialog:dialog.destroy()
                window.bridge=None;window.on_close()
            return False

        GLib.timeout_add(600,exercise)
        Gtk.main()
        print(json.dumps(checks,ensure_ascii=False))
        return 0 if len(checks)>=14 and all(value is True for value in checks.values()) else 1


if __name__=='__main__':raise SystemExit(main())
