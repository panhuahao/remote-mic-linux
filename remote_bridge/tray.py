# SPDX-License-Identifier: GPL-3.0-only
"""Ubuntu StatusNotifier indicator; hiding never stops the bridge."""
import gi
from gi.repository import Gtk, GLib
from .config import ROOT
from .identity import APP_ID, APP_NAME
from .i18n import msg

class Tray:
    def __init__(self, window):
        self.window = window
        self.indicator = None
        self.state = '尚未连接'
        self.recording = False
        self.was_connected = False
        try:
            gi.require_version('AyatanaAppIndicator3', '0.1')
            from gi.repository import AyatanaAppIndicator3 as Indicator
        except (ImportError, ValueError):
            window.log('通知栏组件不可用；请安装 gir1.2-ayatanaappindicator3-0.1。关闭窗口将退出。')
            return
        self.api = Indicator
        self.indicator = Indicator.Indicator.new(APP_ID, str(ROOT/'assets/remote-mic-linux-symbolic.svg'), Indicator.IndicatorCategory.APPLICATION_STATUS)
        self.indicator.set_title(APP_NAME)
        self.menu = Gtk.Menu()
        self.status_item = window.translated(Gtk.MenuItem(),'尚未连接')
        self.status_item.set_sensitive(False)
        self.menu.append(self.status_item)
        self.menu.append(Gtk.SeparatorMenuItem())
        self.add('打开 Remote Mic Linux', window.show_window)
        self.add('连接遥控器', window.on_start)
        self.add('停止连接', window.on_stop)
        self.menu.append(Gtk.SeparatorMenuItem())
        self.add('退出 Remote Mic Linux', window.on_close)
        self.menu.show_all()
        self.indicator.set_menu(self.menu)
        self.indicator.set_status(Indicator.IndicatorStatus.ACTIVE)
        self.indicator.connect('connection-changed', self.connection_changed)
        window.i18n.listeners.append(self.update)

    def add(self, label, callback):
        item = self.window.translated(Gtk.MenuItem(),label)
        item.connect('activate', lambda *_: callback())
        self.menu.append(item)

    @property
    def available(self):
        return self.indicator is not None and self.indicator.get_property('connected')

    def connection_changed(self, _indicator, connected):
        # If a desktop extension disappears, do not strand a hidden application.
        if self.was_connected and not connected and not self.window.closing:
            self.window.show_window()
        self.was_connected = connected

    def update(self, state=None, recording=None):
        if state is not None:self.state = state
        if recording is not None:self.recording = recording
        if self.indicator is None:return
        description = '正在接收语音 · 松开结束' if self.recording else self.state
        self.window.translated(self.status_item,description)
        asset = 'remote-mic-recording-symbolic.svg' if self.recording else 'remote-mic-linux-symbolic.svg'
        self.indicator.set_icon_full(str(ROOT/'assets'/asset), APP_NAME+' · '+self.window.i18n.text(description))

    def close(self):
        if self.indicator:
            self.indicator.set_status(self.api.IndicatorStatus.PASSIVE)
            self.menu.destroy()
