# SPDX-License-Identifier: GPL-3.0-only
import copy
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Gio
from evdev import ecodes
from .actions import PRESETS
from .config import validate_action

class ActionDialog(Gtk.Dialog):
    def __init__(self, parent, title, action, optional=False):
        super().__init__(title=title, transient_for=parent, modal=True)
        self.get_style_context().add_class('bridge-app')
        self.add_buttons("取消", Gtk.ResponseType.CANCEL, "应用", Gtk.ResponseType.OK)
        self.get_widget_for_response(Gtk.ResponseType.OK).get_style_context().add_class('primary')
        self.set_default_size(520, 240)
        box = self.get_content_area(); box.set_spacing(12); box.set_border_width(18)
        self.choice = Gtk.ComboBoxText()
        if optional:self.choice.append("none", "不设置此手势")
        for index, (name, keys) in enumerate(PRESETS):self.choice.append(str(index), name)
        self.choice.append("custom", "自定义快捷键"); self.choice.append("app", "打开已安装的应用")
        box.pack_start(self.choice, False, False, 0)
        self.entry = Gtk.Entry();self.entry.set_placeholder_text("例如 Ctrl+Alt+Space 或 KEY_LEFTCTRL+KEY_V")
        box.pack_start(self.entry, False, False, 0)
        self.record = Gtk.ToggleButton(label="录制快捷键");self.record.connect("toggled", self.recording)
        box.pack_start(self.record, False, False, 0)
        self.app = Gtk.ComboBoxText()
        self.apps = {a.get_id():a for a in Gio.AppInfo.get_all() if a.should_show() and a.get_id()}
        for key, app in sorted(self.apps.items(), key=lambda x: x[1].get_display_name().casefold()):
            self.app.append(key, app.get_display_name())
        box.pack_start(self.app, False, False, 0)
        self.info = Gtk.Label(label="快捷键只执行一次；组合键会自动释放。", xalign=0)
        self.info.set_line_wrap(True); box.pack_start(self.info, False, False, 0)
        self.choice.connect("changed", self.changed); self.connect("key-press-event", self.key_event)
        selected = "custom"
        if action is None:selected = "none" if optional else "0"
        elif isinstance(action, dict):selected = "app"; self.app.set_active_id(action["app"])
        else:
            self.entry.set_text("+".join(action))
            for index, (_,keys) in enumerate(PRESETS):
                if keys == action:selected = str(index); break
        self.choice.set_active_id(selected);self.show_all();self.changed()

    def changed(self, *_):
        custom = self.choice.get_active_id() == "custom"
        self.entry.set_sensitive(custom); self.record.set_sensitive(custom)
        self.app.set_sensitive(self.choice.get_active_id() == "app")
        self.entry.set_visible(custom);self.record.set_visible(custom)
        self.app.set_visible(self.choice.get_active_id() == "app")

    def recording(self, *_):
        self.record.set_label("请按下所需组合键…" if self.record.get_active() else "录制快捷键")

    def key_event(self, _, event):
        if not self.record.get_active():return False
        key = ecodes.KEY.get(event.hardware_keycode - 8)
        if isinstance(key, list):key = key[0]
        if not key or key in ("KEY_LEFTCTRL", "KEY_RIGHTCTRL", "KEY_LEFTALT", "KEY_RIGHTALT", "KEY_LEFTSHIFT", "KEY_RIGHTSHIFT", "KEY_LEFTMETA", "KEY_RIGHTMETA"):return True
        mods = [(Gdk.ModifierType.CONTROL_MASK,"KEY_LEFTCTRL"),(Gdk.ModifierType.MOD1_MASK,"KEY_LEFTALT"),
                (Gdk.ModifierType.SHIFT_MASK,"KEY_LEFTSHIFT"),(Gdk.ModifierType.SUPER_MASK,"KEY_LEFTMETA")]
        self.entry.set_text("+".join([name for mask,name in mods if event.state & mask]+[key]))
        self.record.set_active(False);return True

    def value(self):
        choice = self.choice.get_active_id()
        if choice == "none":return None
        if choice == "app":
            app = self.apps.get(self.app.get_active_id())
            if not app:raise ValueError("请选择已安装的应用")
            result = {"app": app.get_id(), "name": app.get_display_name()}
        elif choice == "custom":
            aliases = {"CTRL":"KEY_LEFTCTRL", "ALT":"KEY_LEFTALT", "SHIFT":"KEY_LEFTSHIFT", "SUPER":"KEY_LEFTMETA", "WIN":"KEY_LEFTMETA", "ESC":"KEY_ESC"}
            result = [aliases.get(x.strip().upper(), x.strip().upper() if x.strip().upper().startswith("KEY_") else "KEY_"+x.strip().upper()) for x in self.entry.get_text().split("+") if x.strip()]
        else:result = copy.deepcopy(PRESETS[int(choice)][1])
        validate_action(result);return result
