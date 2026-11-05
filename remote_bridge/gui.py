# SPDX-License-Identifier: GPL-3.0-only
import asyncio
import copy
import queue
import signal
import threading
from datetime import datetime
from pathlib import Path
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Gio
from . import config, credentials, __version__
from .actions import REMOTE_KEYS, ALIASES, label
from .action_editor import ActionDialog
from .bridge import Bridge, scan
from .focus import Focus
from .text_input import TextInserter
from .clipboard import GtkClipboard
from .ui import Layout
from .identity import APP_ID, APP_NAME, acquire_lock, prepare
from .tray import Tray
from .desktop import launch_context
from .i18n import Translator, load_locale, save_locale, msg, message_key, error_message

def caption(text):
    widget = Gtk.Label(label=text, xalign=0);widget.set_line_wrap(True);return widget

def page():
    widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12);widget.set_border_width(18);return widget

def voice_source(voice):
    if voice['mode']=='local':return msg('本机离线 · SenseVoice')
    if voice['mode']=='external':return msg('外部应用')
    return msg('有道 · {service}',service=msg({'large':'大模型实时识别','short':'短语音识别','realtime_short':'实时短语音识别','realtime':'普通实时识别'}[voice['youdao_api']]))

def voice_choice(voice):
    return (voice['mode'],voice.get('youdao_api') if voice['mode']=='youdao' else None,
            voice.get('youdao_model') if voice['mode']=='youdao' and voice.get('youdao_api')=='large' else None)

class Window(Layout, Gtk.Window):
    def caption(self, value):
        return self.display(caption(''),value)

    def combo(self, items, value):
        return self.i18n.combo(Gtk.ComboBoxText(),items,value)

    def field(self, box, title, widget):
        row=Gtk.Box(spacing=12);name=self.caption(title);name.set_size_request(140,-1)
        row.pack_start(name,False,False,0);row.pack_start(widget,True,True,0);box.pack_start(row,False,False,0)

    def set_ui_language(self, locale):
        save_locale(locale)
        self.i18n.set_locale(locale)

    def toggle_ui_language(self, *_):
        try:self.set_ui_language('en' if self.i18n.locale=='zh_CN' else 'zh_CN')
        except OSError as exc:self.log(msg('界面语言未保存：{error}',error=error_message(exc)))

    def __init__(self):
        super().__init__(title="Remote Mic Linux")
        self.set_default_size(1060, 800);self.set_border_width(18)
        self.messages = queue.Queue();self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True);self.thread.start()
        self.bridge = self.future = self.task = self.inserter = None
        self.i18n=Translator(load_locale());self.log_history=[]
        self.i18n.listeners.append(self.refresh_logs)
        self.settings = config.read();self.closing = False;self.generation = 0;self.capture_focus = {};self.input_epoch = 0
        self.capture_sources={};self.result_source=None;self.selected_voice_choice=None;self.pending_voice_selection=False
        self.focus = Focus();self.clipboard = GtkClipboard();self.restart_source = None;self.mapping_buttons = {}
        self.connect("delete-event", self.on_delete)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: (self.on_close(),False)[1])
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: (self.on_close(),False)[1])
        self.build_shell()
        self.tray = Tray(self)
        GLib.timeout_add(80,self.poll)

    def edit_action(self,key,kind,name):
        action=self.settings["mapping"].get(key,[key]) if kind=="single" else self.settings.get("gestures",{}).get(key,{}).get(kind)
        dialog=ActionDialog(self,msg('{key} · {gesture}',key=msg(name),gesture=msg({'single':'单击','double':'双击','hold':'长按'}[kind])),action,kind!="single")
        while dialog.run()==Gtk.ResponseType.OK:
            try:
                value=dialog.value()
                for target in [key]+ALIASES.get(key,[]):
                    if kind=="single":self.settings["mapping"][target]=value
                    elif value is None:self.settings.setdefault("gestures",{}).setdefault(target,{}).pop(kind,None)
                    else:self.settings.setdefault("gestures",{}).setdefault(target,{})[kind]=value
                self.refresh_mapping();break
            except Exception as exc:dialog.i18n.bind(dialog.info,'set_text',error_message(exc))
        dialog.destroy()

    def build_voice(self):
        voice=self.settings["voice"];box=page();scroll=Gtk.ScrolledWindow();scroll.add(box);self.notebook.append_page(scroll,self.caption("语音设置"))
        self.backend=self.combo([("local","本机离线 · SenseVoice"),("youdao","有道智云 · 在线识别"),("external","外部应用 · Vokie 等")],voice["mode"]);self.field(box,"识别方式",self.backend)
        self.auto_insert=self.translated(Gtk.CheckButton(),"识别后输入到原来的文本框（不按回车、不自动发送）");self.auto_insert.set_active(voice["auto_insert"]);box.pack_start(self.auto_insert,False,False,0)
        self.paste_mode=self.combo([("normal","普通应用：Ctrl+V"),("terminal","终端：Ctrl+Shift+V")],"terminal" if "KEY_LEFTSHIFT" in voice["paste_shortcut"] else "normal");self.field(box,"输入快捷键",self.paste_mode)
        self.local_box=page();box.pack_start(self.local_box,False,False,0)
        self.language=self.combo([("auto","自动检测"),("zh","普通话"),("en","英语"),("yue","粤语"),("ja","日语"),("ko","韩语")],voice["language"]);self.field(self.local_box,"本地识别语言",self.language)
        self.model_path=Gtk.Entry();self.model_path.set_text(voice["model_dir"]);self.field(self.local_box,"模型目录",self.model_path)
        self.model_status=self.caption("");self.local_box.pack_start(self.model_status,False,False,0)
        self.local_box.pack_start(self.caption("离线模式不上传语音；首次使用需安装模型。单段最长 60 秒。"),False,False,0)
        self.cloud_box=page();box.pack_start(self.cloud_box,False,False,0)
        self.cloud_api=self.combo([("large","大模型实时识别（推荐）"),("short","短语音识别：松开后上传"),("realtime_short","实时短语音识别"),("realtime","普通实时语音识别")],voice["youdao_api"]);self.field(self.cloud_box,"有道服务",self.cloud_api)
        self.cloud_model=self.combo([("multi-lang-stream-fast-v1","快速模型 · 低延迟"),("multi-lang-stream-v1","标准模型 · 优先断句与准确率")],voice["youdao_model"]);self.field(self.cloud_box,"大模型选项",self.cloud_model)
        self.cloud_language=Gtk.ComboBoxText.new_with_entry()
        for lang in ("zh-CHS","auto","en","ja","yue","zh-CHS2","en-class"):self.cloud_language.append_text(lang)
        self.cloud_language.get_child().set_text(voice["youdao_language"]);self.field(self.cloud_box,"语言代码",self.cloud_language)
        self.cloud_box.pack_start(self.caption("大模型支持 auto / zh-CHS / en；实时短语音支持 zh-CHS / en。普通实时请依其文档选择语言代码。"),False,False,0)
        secret=credentials.read();self.app_id=Gtk.Entry();self.app_id.set_text(secret["app_id"])
        self.app_secret=Gtk.Entry();self.app_secret.set_visibility(False);self.app_secret.set_input_purpose(Gtk.InputPurpose.PASSWORD);self.app_secret.set_text(secret["secret"])
        self.field(self.cloud_box,"应用 ID",self.app_id);self.field(self.cloud_box,"应用密钥",self.app_secret)
        self.cloud_box.pack_start(self.caption("保存时凭据写入本机独立 0600 文件，仅当前系统用户可读，未加密。不要在聊天中发送密钥。"),False,False,0)
        self.cloud_box.pack_start(self.caption("选择有道后，按语音键会通过加密连接上传音频，并消耗有道额度；需要应用开通所选服务。不会自动切换或重复请求其他收费服务。"),False,False,0)
        self.external_box=page();box.pack_start(self.external_box,False,False,0)
        self.shortcut=Gtk.Entry();self.shortcut.set_placeholder_text("KEY_LEFTCTRL+KEY_LEFTALT+KEY_SPACE");self.shortcut.set_text("+".join(self.settings.get("voice_shortcut",[])));self.field(self.external_box,"外部触发键",self.shortcut)
        self.mode=self.combo([("hold","按住期间保持快捷键"),("toggle","开始 / 结束各点击一次")],self.settings.get("voice_shortcut_mode","hold"));self.field(self.external_box,"触发方式",self.mode)
        self.external_box.pack_start(self.caption("外部应用选择 Ubuntu Remote Microphone；Vokie 已验证启动，登录及识别尚未验证。"),False,False,0)
        self.backend.connect("changed",self.backend_changed);self.cloud_api.connect("changed",self.backend_changed);self.cloud_model.connect("changed",self.backend_changed);GLib.idle_add(self.backend_changed)

    def backend_changed(self,*_):
        mode=self.backend.get_active_id();self.local_box.set_visible(mode=="local");self.cloud_box.set_visible(mode=="youdao");self.external_box.set_visible(mode=="external")
        self.cloud_model.set_sensitive(self.cloud_api.get_active_id()=="large")
        directory=Path(self.model_path.get_text()).expanduser();ready=all((directory/f).is_file() for f in ("model.int8.onnx","tokens.txt"))
        self.display(self.model_status,"模型文件已安装" if ready else "模型文件尚未就绪")
        selection={'mode':mode,'youdao_api':self.cloud_api.get_active_id(),'youdao_model':self.cloud_model.get_active_id()}
        selected=voice_choice(selection);pending=selected!=voice_choice(self.settings['voice'])
        changed=selected!=self.selected_voice_choice;was_pending=self.pending_voice_selection
        self.selected_voice_choice=selected;self.pending_voice_selection=pending
        if pending and (changed or not was_pending):
            # A switch to local must not leave the previous cloud recognizer running.
            self.on_stop()
            self.display(self.voice,'识别方式已更改 · 等待应用')
            self.display(self.source_status,msg('已选择：{source}（尚未应用）',source=voice_source(selection)))
            self.display(self.asr_status,'原识别已停止，请点击“保存并连接”启用新方式。')
            self.display(self.input_status,'新识别方式尚未应用，本次不会自动输入。')
            if self.result_source:self.display(self.result_heading,msg('上一段结果 · {source}',source=self.result_source))
        elif was_pending and not pending:
            self.display(self.source_status,msg('已选择：{source}',source=voice_source(selection)))
            self.display(self.asr_status,'请保存并连接以启动识别。')
        return False

    def emit(self,kind,data):self.messages.put((self.generation,kind,data))

    def log(self,message):
        self.log_history.append((datetime.now().strftime("%H:%M:%S "),message))
        self.log_history=self.log_history[-300:]
        self.refresh_logs()

    def refresh_logs(self):
        if hasattr(self,'logs'):
            self.logs.get_buffer().set_text(''.join(stamp+self.i18n.text(message)+'\n' for stamp,message in self.log_history))

    def clear_logs(self,*_):
        self.log_history.clear();self.refresh_logs()

    def poll(self):
        for _ in range(250):
            try:gen,kind,data=self.messages.get_nowait()
            except queue.Empty:break
            if gen!=self.generation:continue
            if kind=="status":self.set_connection_status(data)
            elif kind=="log":self.log(data)
            elif kind=="asr_status":
                self.display(self.asr_status,data)
                if message_key(data)=='有道识别失败：{error}' or message_key(data).startswith('有道识别失败：'):
                    self.display(self.result_heading,msg('未完成的预览 · {source}',source=self.result_source or voice_source(self.settings['voice'])))
                    self.display(self.input_status,'本次识别未最终确认，未自动输入；可手动复制预览或重新说话。')
            elif kind=="input_status":self.display(self.input_status,data)
            elif kind=="devices":
                self.devices.remove_all()
                for device in data:self.devices.append(device["address"],device["name"]+" · "+device["address"][-5:])
                if len(data)==1:self.devices.set_active(0)
                self.scan_button.set_sensitive(True)
            elif kind=="address":self.address.set_text(data)
            elif kind=="level":self.level.set_value(data)
            elif kind=="voice":
                self.display(self.voice,"正在接收语音… 松开结束" if data else "待机 · 按住语音键说话")
                self.tray.update(recording=bool(data))
                if not data:self.level.set_value(0)
            elif kind=="capture" and data["active"]:
                self.result.get_buffer().set_text('')
                self.result_source=voice_source(self.settings['voice'])
                self.capture_sources[data['id']]=self.result_source
                self.display(self.source_status,msg('当前识别方式：{source}',source=self.result_source))
                self.display(self.result_heading,msg('实时预览 · {source}',source=self.result_source))
                self.display(self.input_status,'正在录音；请保持目标输入框的焦点。')
                self.capture_focus[data["id"]]=self.focus.snapshot()
                if len(self.capture_focus)>8:
                    oldest=next(iter(self.capture_focus));self.capture_focus.pop(oldest);self.capture_sources.pop(oldest,None)
            elif kind=="invalidate":self.capture_focus.clear();self.capture_sources.clear();self.input_epoch+=1
            elif kind=="partial":self.result.get_buffer().set_text(data)
            elif kind=="transcript":
                self.result_source=self.capture_sources.pop(data['id'],voice_source(self.settings['voice']))
                self.display(self.result_heading,msg('最终识别结果 · {source}',source=self.result_source))
                self.result.get_buffer().set_text(data["text"]);token=self.capture_focus.pop(data["id"],None)
                if data["text"] and self.settings["voice"]["auto_insert"]:self.insert(data["text"],token,gen)
                self.log(msg("识别完成：音频 {audio:.1f} 秒，处理 {elapsed:.1f} 秒",audio=data["audio_seconds"],elapsed=data["elapsed"]))
            elif kind=="launch":
                try:
                    app=Gio.DesktopAppInfo.new(data)
                    if app:app.launch([],launch_context())
                    else:self.log(msg("未找到应用：{app}",app=data))
                except Exception as exc:self.log(msg("启动应用失败：{error}",error=error_message(exc)))
            elif kind=="key":
                for key,button in self.remote_buttons.items():
                    if data in [key]+ALIASES.get(key,[]):
                        context=button.get_style_context();context.add_class("key-active");GLib.timeout_add(450,lambda c=context:(c.remove_class("key-active"),False)[1])
        if self.closing and (self.future is None or self.future.done()):
            self.tray.close()
            self.focus.close();self.loop.call_soon_threadsafe(self.loop.stop)
            if self.inserter:threading.Thread(target=self.inserter.close,daemon=True).start()
            application=self.get_application()
            if application:application.quit()
            else:Gtk.main_quit()
            return False
        return True

    def insert(self,text,token,generation):
        if not self.focus.valid(token):self.display(self.input_status,"目标窗口或输入框已变化；结果已保留。请先点入目标输入框再说话。");return
        epoch=self.input_epoch
        valid=lambda:not self.closing and generation==self.generation and epoch==self.input_epoch and self.focus.valid(token)
        try:
            if self.inserter is None:self.inserter=TextInserter(self.clipboard)
        except Exception as exc:self.display(self.input_status,msg("输入设备不可用：{error}",error=error_message(exc)));return
        keys=copy.deepcopy(self.settings["voice"]["paste_shortcut"])
        def work():
            try:
                success=self.inserter.insert(text,keys,valid);message=msg("已发送粘贴快捷键（未按回车）" if success else "目标焦点变化，已取消输入")
            except Exception as exc:message=msg("输入失败：{error}",error=error_message(exc))
            self.messages.put((generation,"input_status",message))
        threading.Thread(target=work,daemon=True).start()

    def result_text(self):
        b=self.result.get_buffer();return b.get_text(*b.get_bounds(),True)

    def copy_result(self,*_):
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(self.result_text(),-1);self.display(self.input_status,"结果已复制")

    def delayed_insert(self,*_):
        text=self.result_text();gen=self.generation
        if not text:return
        self.display(self.input_status,"请在 3 秒内切换到目标文本框…")
        def later():
            if gen==self.generation and not self.closing:self.insert(text,self.focus.snapshot(),gen)
            return False
        GLib.timeout_add(3000,later)

    def select_device(self,_):
        address=self.devices.get_active_id()
        if address:self.address.set_text(address)

    def on_scan(self,_):
        self.scan_button.set_sensitive(False)
        async def scanning():
            try:self.emit("devices",await scan())
            except Exception as exc:self.emit("log",error_message(exc));self.emit("devices",[])
        asyncio.run_coroutine_threadsafe(scanning(),self.loop)

    def collect(self):
        settings=copy.deepcopy(self.settings)
        settings.update(address=self.address.get_text().strip(),mapping_enabled=self.enabled.get_active(),voice_shortcut=[v.strip() for v in self.shortcut.get_text().split("+") if v.strip()],voice_shortcut_mode=self.mode.get_active_id())
        settings["voice"].update(mode=self.backend.get_active_id(),language=self.language.get_active_id(),model_dir=self.model_path.get_text().strip(),auto_insert=self.auto_insert.get_active(),paste_shortcut=["KEY_LEFTCTRL"]+(["KEY_LEFTSHIFT"] if self.paste_mode.get_active_id()=="terminal" else [])+["KEY_V"],youdao_api=self.cloud_api.get_active_id(),youdao_model=self.cloud_model.get_active_id(),youdao_language=self.cloud_language.get_child().get_text().strip())
        config.validate(settings);credentials.save(self.app_id.get_text(),self.app_secret.get_text());config.save(settings);self.settings=settings;return settings

    def on_start(self,_=None):
        if self.closing:return
        try:settings=self.collect()
        except Exception as exc:self.log(msg("配置未保存：{error}",error=error_message(exc)));self.set_connection_status("配置有误，请查看日志");return
        self.on_stop()
        def start_when_ready():
            if self.closing:return False
            if self.future and not self.future.done():return True
            self.restart_source=None;generation=self.generation;notify=lambda kind,value:self.messages.put((generation,kind,value))
            self.display(self.source_status,msg('当前识别方式：{source}',source=voice_source(settings['voice'])))
            self.display(self.asr_status,'正在准备识别…')
            async def run():
                self.task=asyncio.current_task();self.bridge=Bridge(settings,notify)
                try:await self.bridge.run()
                except asyncio.CancelledError:pass
                except Exception as exc:notify("log",error_message(exc));notify("status","启动失败，请查看日志")
                finally:self.task=None
            self.future=asyncio.run_coroutine_threadsafe(run(),self.loop);return False
        self.restart_source=GLib.timeout_add(100,start_when_ready);self.backend_changed()

    def on_stop(self,_=None):
        if self.restart_source:GLib.source_remove(self.restart_source);self.restart_source=None
        self.generation+=1;self.capture_focus.clear();self.capture_sources.clear();self.set_connection_status("已停止 / 正在释放连接");self.display(self.asr_status,"识别已停止")
        self.display(self.source_status,'识别已停止')
        if self.result_source:self.display(self.result_heading,msg('上一段结果 · {source}',source=self.result_source))
        def stop():
            if self.bridge:self.bridge.stop_event.set()
            if self.task:self.task.cancel()
        self.loop.call_soon_threadsafe(stop)

    def show_window(self,*_):
        if self.closing:return
        self.show_all();self.backend_changed();self.deiconify()
        if isinstance(self.get_display(), Gdk.Display):
            try:
                gi.require_version('GdkX11','3.0')
                from gi.repository import GdkX11
                if isinstance(self.get_display(),GdkX11.X11Display):
                    self.present_with_time(GdkX11.x11_get_server_time(self.get_window()))
                    return
            except (ImportError, ValueError):pass
        self.present()

    def hide_to_tray(self,*_):
        if self.tray.available:
            self.hide()
        else:
            self.log('通知栏当前不可用，请检查 Ubuntu AppIndicators 扩展。可使用“退出应用”结束程序。')

    def on_delete(self,*_):
        if self.tray.available:self.hide()
        else:self.on_close()
        return True

    def on_close(self,*_):
        if not self.closing:
            self.closing=True;self.on_stop();self.hide()
        return True

def main(autostart=False):
    prepare();Gdk.set_program_class(APP_ID)
    application=Gtk.Application(application_id=APP_ID)
    window=lock=None
    def activate(app):
        nonlocal window,lock
        if window is None:
            lock=acquire_lock()
            window=Window();window.set_application(app)
            for name,callback in (('show',window.show_window),('hide',window.hide_to_tray),('quit',window.on_close)):
                action=Gio.SimpleAction.new(name,None)
                action.connect('activate',lambda _,parameter,fn=callback:fn())
                app.add_action(action)
            if autostart:GLib.idle_add(lambda:(window.on_start(),False)[1])
        window.show_window()
    application.connect('activate',activate)
    try:application.run([APP_ID])
    finally:
        if lock:lock.close()
