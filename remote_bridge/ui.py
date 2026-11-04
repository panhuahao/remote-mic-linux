# SPDX-License-Identifier: GPL-3.0-only
"""Presentation layer; device, recognition and input logic live in gui.py."""
from pathlib import Path
from gi.repository import Gtk, Gdk, GdkPixbuf
from . import config, __version__
from .actions import REMOTE_KEYS, label
from .identity import REPOSITORY_URL

def style(widget, *classes):
    for name in classes:
        widget.get_style_context().add_class(name)
    return widget

def text(value, *classes):
    widget=Gtk.Label(label=value, xalign=0)
    widget.set_line_wrap(True)
    widget.set_max_width_chars(62)
    return style(widget, *classes)

def page():
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16)
    box.set_margin_start(24);box.set_margin_end(24)
    box.set_margin_top(18);box.set_margin_bottom(14)
    return box

def card(title=None, subtitle=None):
    box=style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12),'card')
    if title:box.pack_start(text(title,'card-title'),False,False,0)
    if subtitle:box.pack_start(text(subtitle,'hint'),False,False,0)
    return box

def button(label, icon=None, *classes):
    widget=style(Gtk.Button(label=label),*classes)
    if icon:
        widget.set_image(Gtk.Image.new_from_icon_name(icon,Gtk.IconSize.BUTTON))
        widget.set_always_show_image(True)
    return widget

class Layout:
    PAGES=(
        ('按键映射','input-keyboard-symbolic','让每一个按键，都更顺手。'),
        ('语音输入','audio-input-microphone-symbolic','按住说话，松开后输入到当前文本框。'),
        ('测试与结果','text-x-generic-symbolic','查看识别状态，轻松验证语音输入。'),
        ('连接日志','utilities-terminal-symbolic','连接与运行状态，清晰可查。'),
    )

    def build_shell(self):
        self.set_default_size(1120,800);self.set_size_request(980,660)
        self.set_border_width(0);style(self,'bridge-app')
        css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).with_name('theme.css')))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        icon=config.ROOT/'assets/remote-mic-linux.png'
        self.set_icon_from_file(str(icon))
        layout=Gtk.Box();self.add(layout)
        sidebar=style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL),'sidebar')
        sidebar.set_size_request(184,-1);layout.pack_start(sidebar,False,False,0)
        brand=Gtk.Box(spacing=9)
        brand.pack_start(Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(icon),40,40,True)),False,False,0)
        names=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
        names.pack_start(text('Remote Mic','brand-name'),False,False,0)
        names.pack_start(text('LINUX','brand-subtitle'),False,False,0)
        brand.pack_start(names,False,False,0);sidebar.pack_start(brand,False,False,0)
        sidebar.pack_start(text('工作空间','sidebar-section'),False,False,0)
        self.nav_buttons=[]
        for index,(title,icon_name,_) in enumerate(self.PAGES):
            nav=style(Gtk.Button(),'nav-item');row=Gtk.Box(spacing=12)
            row.pack_start(Gtk.Image.new_from_icon_name(icon_name,Gtk.IconSize.BUTTON),False,False,0)
            row.pack_start(Gtk.Label(label=title,xalign=0),True,True,0);nav.add(row)
            nav.connect('clicked',lambda _,i=index:self.navigate(i))
            sidebar.pack_start(nav,False,False,0);self.nav_buttons.append(nav)
        sidebar.pack_start(Gtk.Box(),True,True,0)
        device=style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8),'sidebar-device')
        device.pack_start(text('蓝牙遥控器','sidebar-device-title'),False,False,0)
        self.status=text('尚未连接','sidebar-note');self.status.set_max_width_chars(18)
        device.pack_start(self.status,False,False,0)
        device.pack_start(text('Remote 2 已实测\n2 Pro 待验证','sidebar-note'),False,False,0)
        sidebar.pack_start(device,False,False,0)
        footer=style(Gtk.Box(spacing=10),'sidebar-footer')
        footer.pack_start(text('v'+__version__,'sidebar-version'),True,True,0)
        github=style(Gtk.LinkButton(uri=REPOSITORY_URL),'github-link')
        github.set_image(Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(config.ROOT/'assets/github-mark.png'),18,18,True)))
        github.set_always_show_image(True);github.set_label('')
        github.set_tooltip_text('GitHub · Remote Mic Linux（私有仓库，需登录有权限的账号）')
        github.get_accessible().set_name('在 GitHub 打开 Remote Mic Linux 项目')
        from .desktop import open_uri
        github.connect('activate-link',lambda widget:(open_uri(widget.get_uri()),True)[1])
        footer.pack_end(github,False,False,0);sidebar.pack_start(footer,False,False,0)
        main=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);layout.pack_start(main,True,True,0)
        header=style(Gtk.Box(spacing=20),'page-header');main.pack_start(header,False,False,0)
        titles=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=7)
        self.page_title=text('按键映射','page-title');self.page_subtitle=text(self.PAGES[0][2],'subtitle')
        titles.pack_start(self.page_title,False,False,0);titles.pack_start(self.page_subtitle,False,False,0)
        header.pack_start(titles,True,True,0)
        self.connection_badge=text('●  未连接','status-pill');self.connection_badge.set_valign(Gtk.Align.CENTER)
        header.pack_start(self.connection_badge,False,False,0)
        menu_button=style(Gtk.MenuButton(),'quiet')
        menu_button.set_image(Gtk.Image.new_from_icon_name('open-menu-symbolic',Gtk.IconSize.BUTTON))
        menu_button.set_tooltip_text('后台运行与退出')
        menu=Gtk.Menu()
        for title,callback in (('收起到通知栏',self.hide_to_tray),('退出应用',self.on_close)):
            item=Gtk.MenuItem(label=title);item.connect('activate',lambda _,fn=callback:fn());menu.append(item)
        menu.show_all();menu_button.set_popup(menu);header.pack_end(menu_button,False,False,0)
        toolbar=style(Gtk.Box(spacing=8),'connection-bar');toolbar.set_margin_start(24);toolbar.set_margin_end(24)
        toolbar.pack_start(Gtk.Image.new_from_icon_name('bluetooth-active-symbolic',Gtk.IconSize.BUTTON),False,False,5)
        self.address=Gtk.Entry();self.address.set_width_chars(19);self.address.set_placeholder_text('已配对设备的蓝牙地址')
        self.address.set_text(self.settings.get('address',''));toolbar.pack_start(self.address,True,True,0)
        self.scan_button=button('扫描','view-refresh-symbolic');self.scan_button.connect('clicked',self.on_scan);toolbar.pack_start(self.scan_button,False,False,0)
        self.devices=Gtk.ComboBoxText();self.devices.set_tooltip_text('选择扫描到的遥控器');self.devices.connect('changed',self.select_device);toolbar.pack_start(self.devices,False,False,0)
        start=button('保存并连接',None,'primary');start.connect('clicked',self.on_start);toolbar.pack_start(start,False,False,0)
        stop=button('停止',None,'quiet');stop.connect('clicked',self.on_stop);toolbar.pack_start(stop,False,False,0)
        main.pack_start(toolbar,False,False,0)
        self.notebook=Gtk.Notebook();self.notebook.set_show_tabs(False);self.notebook.set_show_border(False)
        main.pack_start(self.notebook,True,True,0)
        self.build_mapping();self.build_voice();self.build_result();self.build_logs()
        for box,title in ((self.local_box,'本机离线识别'),(self.cloud_box,'有道智云'),(self.external_box,'连接外部应用')):
            style(box,'card');heading=text(title,'card-title');box.pack_start(heading,False,False,0);box.reorder_child(heading,0)
        main.pack_start(text('按住语音键说话  ·  松开即可输入  ·  不自动回车或发送','bottom-strip'),False,False,0)
        self.navigate(0)

    def navigate(self,index):
        self.notebook.set_current_page(index)
        self.page_title.set_text(self.PAGES[index][0]);self.page_subtitle.set_text(self.PAGES[index][2])
        for i,nav in enumerate(self.nav_buttons):
            context=nav.get_style_context()
            context.add_class('active') if i==index else context.remove_class('active')

    def set_connection_status(self,value):
        self.status.set_text(value)
        if hasattr(self,'tray'):self.tray.update(state=value)
        state='';short='未连接'
        if value.startswith('已连接'):state='connected';short='已连接'
        elif any(x in value for x in ('失败','有误')):state='error';short='需要检查'
        elif any(x in value for x in ('扫描','协商','等待')):state='working';short='连接中'
        elif value.startswith('已停止'):short='已停止'
        context=self.connection_badge.get_style_context()
        for name in ('connected','working','error'):context.remove_class(name)
        if state:context.add_class(state)
        self.connection_badge.set_text('●  '+short)

    def build_mapping(self):
        outer=page();self.notebook.append_page(outer,Gtk.Label(label='按键映射'))
        top=Gtk.Box(spacing=16);heading=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
        heading.pack_start(text('你的遥控器，你来定义','card-title'),False,False,0)
        heading.pack_start(text('点击动作编辑；修改后保存并连接。','hint'),False,False,0)
        top.pack_start(heading,True,True,0)
        self.enabled=Gtk.CheckButton(label='启用映射');self.enabled.set_active(self.settings.get('mapping_enabled',True))
        top.pack_start(self.enabled,False,False,0);outer.pack_start(top,False,False,0)
        body=Gtk.Box(spacing=18);outer.pack_start(body,True,True,0)
        panel=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=13);panel.set_valign(Gtk.Align.START)
        shell=style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14),'remote-shell')
        model=text('XIAOMI REMOTE','remote-label');model.set_halign(Gtk.Align.CENTER);shell.pack_start(model,False,False,0)
        remote=Gtk.Grid(column_spacing=6,row_spacing=9)
        positions=[(0,0),(2,0),(1,2),(0,3),(1,3),(2,3),(1,4),(0,5),(1,5),(2,5),(0,6),(2,6)]
        self.remote_buttons={}
        for (key,name,icon),(x,y) in zip(REMOTE_KEYS,positions):
            key_button=button(icon,None,'remote-key');key_button.set_tooltip_text(name+' · 编辑单击动作')
            if key=='KEY_ENTER':style(key_button,'remote-ok')
            if key=='KEY_TV':style(key_button,'remote-small')
            key_button.connect('clicked',lambda _,k=key,n=name:self.edit_action(k,'single',n))
            remote.attach(key_button,x,y,1,1);self.remote_buttons[key]=key_button
        mic=style(Gtk.Box(spacing=6),'remote-mic')
        mic.pack_start(Gtk.Image.new_from_icon_name('audio-input-microphone-symbolic',Gtk.IconSize.MENU),False,False,0)
        mic.pack_start(Gtk.Label(label='按住说话'),True,True,0);remote.attach(mic,0,1,3,1)
        shell.pack_start(remote,False,False,0);panel.pack_start(shell,False,False,0)
        hint=text('实体按键会实时高亮','muted');hint.set_halign(Gtk.Align.CENTER);panel.pack_start(hint,False,False,0)
        body.pack_start(panel,False,False,0)
        table=card();table.set_hexpand(True);grid=Gtk.Grid(column_spacing=8,row_spacing=4);grid.set_hexpand(True)
        for col,title in enumerate(('按键','单击 / 常规','双击','长按')):
            header=text(title,'table-header');header.set_hexpand(col>0);grid.attach(header,col,0,1,1)
        for row,(key,name,_) in enumerate(REMOTE_KEYS,1):
            grid.attach(text(name,'mapping-key'),0,row,1,1)
            for col,kind in enumerate(('single','double','hold'),1):
                action=button('',None,'mapping-action');action.set_hexpand(True)
                action.connect('clicked',lambda _,k=key,g=kind,n=name:self.edit_action(k,g,n))
                grid.attach(action,col,row,1,1);self.mapping_buttons[(key,kind)]=action
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC);scroll.add(grid)
        table.pack_start(scroll,True,True,0);body.pack_start(table,True,True,0)
        outer.pack_start(text('双击等待 300 ms  ·  长按阈值 550 ms  ·  语音键保留用于采音','muted'),False,False,0)
        self.refresh_mapping()

    def refresh_mapping(self):
        for (key,kind),action_button in self.mapping_buttons.items():
            action=self.settings['mapping'].get(key,[key]) if kind=='single' else self.settings.get('gestures',{}).get(key,{}).get(kind)
            value='＋ 添加' if action is None else label(action)
            action_button.set_label(value);action_button.set_tooltip_text(value)
            context=action_button.get_style_context()
            context.add_class('unset') if action is None else context.remove_class('unset')

    def build_result(self):
        box=page();self.notebook.append_page(box,Gtk.Label(label='测试与结果'))
        capture=style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10),'capture-card')
        capture.pack_start(text('VOICE INPUT','eyebrow'),False,False,0)
        self.source_status=text('识别方式尚未启动','hint');capture.pack_start(self.source_status,False,False,0)
        self.voice=text('准备就绪，按住语音键说话','voice-state');capture.pack_start(self.voice,False,False,0)
        self.level=Gtk.LevelBar(min_value=0,max_value=1);capture.pack_start(self.level,False,False,0)
        self.asr_status=text('识别尚未启动','hint');capture.pack_start(self.asr_status,False,False,0);box.pack_start(capture,False,False,0)
        result=card();self.result_heading=text('识别结果','card-title')
        result.pack_start(self.result_heading,False,False,0);box.pack_start(result,True,True,0)
        self.result=Gtk.TextView();self.result.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll=Gtk.ScrolledWindow();scroll.set_min_content_height(60);scroll.add(self.result);result.pack_start(scroll,True,True,0)
        actions=Gtk.Box(spacing=8)
        copy=button('复制文字','edit-copy-symbolic');copy.connect('clicked',self.copy_result);actions.pack_start(copy,False,False,0)
        insert=button('3 秒后输入',None,'secondary');insert.set_tooltip_text('点击后，在 3 秒内点入目标文本框')
        insert.connect('clicked',self.delayed_insert);actions.pack_start(insert,False,False,0);result.pack_start(actions,False,False,0)
        self.input_status=text('点入目标文本框后说话，无需切回本窗口。','hint');result.pack_start(self.input_status,False,False,0)
        target=card('安全测试框','点入下方，用遥控器说一句话，验证识别与输入。');box.pack_start(target,True,True,0)
        self.test_entry=Gtk.TextView();self.test_entry.set_wrap_mode(Gtk.WrapMode.WORD_CHAR);self.test_entry.get_accessible().set_name('遥控器语音安全测试框')
        scroll=Gtk.ScrolledWindow();scroll.set_min_content_height(55);scroll.add(self.test_entry);target.pack_start(scroll,True,True,0)

    def build_logs(self):
        box=page();self.notebook.append_page(box,Gtk.Label(label='连接日志'))
        heading=Gtk.Box(spacing=12);heading.pack_start(text('运行记录','card-title'),True,True,0)
        clear=button('清空显示','edit-clear-all-symbolic','quiet');heading.pack_start(clear,False,False,0);box.pack_start(heading,False,False,0)
        box.pack_start(text('仅清空当前视图，不影响连接和已保存设置。','hint'),False,False,0)
        self.logs=style(Gtk.TextView(editable=False,cursor_visible=False,monospace=True),'log-view');self.logs.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        clear.connect('clicked',lambda _:self.logs.get_buffer().set_text(''))
        scroll=Gtk.ScrolledWindow();scroll.add(self.logs);box.pack_start(scroll,True,True,0)
