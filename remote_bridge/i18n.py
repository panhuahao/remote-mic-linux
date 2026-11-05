# SPDX-License-Identifier: GPL-3.0-only
"""Explicit, per-window translations; worker messages retain canonical keys.

The display language is separate from the speech recognition configuration.
Widgets are relabelled in place, so switching languages never reconnects a
remote, clears an editor or changes the current recording session.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile

LOCALES = ("zh_CN", "en")
DEFAULT_LOCALE = "zh_CN"
PREFERENCES = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ubuntu-remote-bridge" / "ui.json"

# Chinese source keys are stable identifiers, never translated before dispatch.
ENGLISH = {'3 秒后输入': 'Insert in 3 seconds',
 'ATVV 已就绪：16 kHz / 单声道 / 帧长 {size}': 'ATVV ready: 16 kHz / mono / frame size {size}',
 'ATVV 帧长异常': 'Invalid ATVV frame size',
 'IP 未在白名单内': 'IP address is not on the allowlist',
 'TV / 应用': 'TV / App',
 'mapping 必须是按键映射对象': 'mapping must be a key mapping object',
 '{key} · {gesture}': '{key} · {gesture}',
 '{key} · 编辑单击动作': '{key} · Edit single press',
 '●  {state}': '●  {state}',
 '●  未连接': '●  Disconnected',
 '上': 'Up',
 '上一段仍在识别，请稍后再说话': 'The previous recording is still being recognized. Please wait.',
 '上一段结果 · {source}': 'Previous result · {source}',
 '上一首': 'Previous track',
 '下': 'Down',
 '下一个控件 / Tab': 'Next control / Tab',
 '下一首': 'Next track',
 '不设置此手势': 'Leave this gesture unset',
 '中文 / English': '中文 / English',
 '主页': 'Home',
 '仅清空当前视图，不影响连接和已保存设置。': 'Clears this view only; connection and saved settings are preserved.',
 '你的遥控器，你来定义': 'Your remote, your controls',
 '例如 Ctrl+Alt+Space 或 KEY_LEFTCTRL+KEY_V': 'For example, Ctrl+Alt+Space or KEY_LEFTCTRL+KEY_V',
 '保存': 'Save',
 '保存并连接': 'Save & Connect',
 '保存时凭据写入本机独立 0600 文件，仅当前系统用户可读，未加密。不要在聊天中发送密钥。': 'Credentials are stored in a separate local file with '
                                                  'permissions 0600, readable only by your system user and '
                                                  'not encrypted. Never share your secret in chat.',
 '停止': 'Stop',
 '停止连接': 'Disconnect',
 '全选': 'Select all',
 '准备就绪，按住语音键说话': 'Ready. Hold the voice button to speak.',
 '切换应用': 'Switch applications',
 '切换界面语言；不影响语音识别语言': 'Switch display language; speech recognition language stays unchanged',
 '剪切': 'Cut',
 '剪贴板设置超时': 'Clipboard update timed out',
 '动作必须是快捷键列表或应用对象': 'An action must be a list of keys or an application object',
 '单击': 'Single press',
 '单击 / 常规': 'Single / Normal',
 '单段语音超过 60 秒，本次未输入，请分段说话': 'Recording exceeded 60 seconds. Nothing was inserted; please use shorter '
                            'recordings.',
 '原识别已停止，请点击“保存并连接”启用新方式。': 'The previous recognizer has stopped. Click Save & Connect to apply the new '
                            'selection.',
 '双击': 'Double press',
 '双击等待 300 ms  ·  长按阈值 550 ms  ·  语音键保留用于采音': 'Double press: 300 ms · Hold: 550 ms · Voice button reserved '
                                              'for audio',
 '发现多个遥控器，请选择设备后连接': 'Multiple remotes found. Select a device and connect.',
 '取消': 'Cancel',
 '右': 'Right',
 '后台运行与退出': 'Background mode and quit',
 '启动失败，请查看日志': 'Could not start. Check the logs.',
 '启动应用失败：{error}': 'Could not launch application: {error}',
 '启用映射': 'Enable mapping',
 '在 GitHub 打开 Remote Mic Linux 项目': 'Open Remote Mic Linux on GitHub',
 '复制': 'Copy',
 '复制文字': 'Copy text',
 '外部应用': 'External application',
 '外部应用 · Vokie 等': 'External application · Vokie, etc.',
 '外部应用模式 · 请在识别应用中选择 Ubuntu Remote Microphone': 'External mode · Select Ubuntu Remote Microphone in your '
                                                'speech application',
 '外部应用选择 Ubuntu Remote Microphone；Vokie 已验证启动，登录及识别尚未验证。': 'Select Ubuntu Remote Microphone in the external '
                                                           'application. Vokie startup was verified; sign-in '
                                                           'and recognition have not been verified.',
 '外部触发键': 'Trigger shortcut',
 '大模型实时识别': 'Large model streaming',
 '大模型实时识别（推荐）': 'Large model streaming (recommended)',
 '大模型支持 auto / zh-CHS / en；实时短语音支持 zh-CHS / en。普通实时请依其文档选择语言代码。': 'Large models support auto / zh-CHS / en; '
                                                                  'short streaming supports zh-CHS / en. For '
                                                                  "standard streaming, see Youdao's "
                                                                  'documented language codes.',
 '大模型选项': 'Large model',
 '安全测试框': 'Safe test field',
 '实体按键会实时高亮': 'Physical button presses light up here',
 '实时短语音识别': 'Short streaming recognition',
 '实时预览 · {source}': 'Live preview · {source}',
 '尚未连接': 'Not connected',
 '屏蔽此按键': 'Disable this key',
 '工作空间': 'WORKSPACE',
 '左': 'Left',
 '已停止': 'Stopped',
 '已停止 / 正在释放连接': 'Stopped / Releasing connection',
 '已发送粘贴快捷键（未按回车）': 'Paste shortcut sent (Enter was not pressed)',
 '已连接': 'Connected',
 '已连接；按住语音键说话': 'Connected; hold the voice button to speak',
 '已选择：{source}': 'Selected: {source}',
 '已选择：{source}（尚未应用）': 'Selected: {source} (not applied)',
 '已配对设备的蓝牙地址': 'Bluetooth address of your paired device',
 '应用': 'Apply',
 '应用 ID': 'App ID',
 '应用 ID 无效': 'Invalid App ID',
 '应用动作必须指向已安装的 .desktop 应用': 'Application actions must refer to an installed .desktop application',
 '应用密钥': 'App secret',
 '应用未绑定该语音服务': 'This speech service is not enabled for your application',
 '应用概览 / Super': 'Application overview / Super',
 '开始 / 结束各点击一次': 'Press once at start and once at end',
 '开始接收遥控器语音': 'Receiving remote microphone audio',
 '当前识别方式：{source}': 'Current recognizer: {source}',
 '录制快捷键': 'Record shortcut',
 '待机 · 按住语音键说话': 'Standby · Hold the voice button to speak',
 '快捷键只执行一次；组合键会自动释放。': 'Shortcuts run once; all keys are released automatically.',
 '快速模型 · 低延迟': 'Fast model · Low latency',
 '手势配置格式错误': 'Invalid gesture configuration',
 '打开 Remote Mic Linux': 'Open Remote Mic Linux',
 '打开已安装的应用': 'Launch an installed application',
 '打开应用：{app}': 'Launch: {app}',
 '扫描': 'Scan',
 '扫描小米遥控器；请进入配对模式…': 'Scanning for Xiaomi remotes; enter pairing mode…',
 '按住期间保持快捷键': 'Hold shortcut while speaking',
 '按住语音键说话  ·  松开即可输入  ·  不自动回车或发送': 'Hold to speak · Release to insert · Never presses Enter or sends',
 '按住说话': 'Hold to speak',
 '按住说话，松开后输入到当前文本框。': 'Hold to speak. Release to insert into the focused text field.',
 '按键': 'Button',
 '按键映射': 'Button mapping',
 '按键映射不可用：{error}': 'Button mapping unavailable: {error}',
 '按键通道已接入：{device}': 'Button input connected: {device}',
 '按键通道断开或不可用：{error}': 'Button input disconnected or unavailable: {error}',
 '按键：{key}': 'Key: {key}',
 '撤销': 'Undo',
 '播放 / 暂停': 'Play / Pause',
 '收起到通知栏': 'Hide to tray',
 '新识别方式尚未应用，本次不会自动输入。': 'The new recognizer is not applied. Automatic insertion is disabled for this '
                        'recording.',
 '方向上': 'Up',
 '方向下': 'Down',
 '方向右': 'Right',
 '方向左': 'Left',
 '无效 ATVV 能力响应': 'Invalid ATVV capability response',
 '无效键名：{name}': 'Invalid key name: {name}',
 '无法启动 PipeWire 虚拟麦克风；请检查用户音频服务': 'Could not start the PipeWire virtual microphone. Check your user audio '
                                  'service.',
 '日语': 'Japanese',
 '旧版 ATVV 能力响应不完整': 'Incomplete legacy ATVV capability response',
 '显示桌面': 'Show desktop',
 '普通实时识别': 'Standard streaming recognition',
 '普通实时语音识别': 'Standard streaming recognition',
 '普通应用：Ctrl+V': 'Applications: Ctrl+V',
 '普通有道接口需指定语言，例如 zh-CHS 或 en': 'Specify a language such as zh-CHS or en for this Youdao service',
 '普通话': 'Mandarin',
 '最终识别结果 · {source}': 'Final result · {source}',
 '有道 · {service}': 'Youdao · {service}',
 '有道已连接 · 正在上传遥控器语音': 'Youdao connected · Uploading remote microphone audio',
 '有道已配置 · 按住说话（联网传音频；权限待首次请求验证）': 'Youdao configured · Hold to speak (audio is uploaded; service access is '
                                  'checked on first use)',
 '有道提前断开，未输入不完整结果': 'Youdao disconnected early; the incomplete result was not inserted',
 '有道提前结束，请重新说话': 'Youdao ended the session early. Please try again.',
 '有道智云': 'Youdao AI Cloud',
 '有道智云 · 在线识别': 'Youdao AI Cloud · Online recognition',
 '有道服务': 'Youdao service',
 '有道未返回启动确认': 'Youdao did not acknowledge the session start',
 '有道识别失败：{error}': 'Youdao recognition failed: {error}',
 '有道识别完成': 'Youdao recognition complete',
 '有道识别尚未配置完成': 'Youdao recognition is not fully configured',
 '有道语言代码格式错误': 'Invalid Youdao language code',
 '有道错误 {code}：{error}': 'Youdao error {code}: {error}',
 '未发现 ATVV 语音通道；请完成系统蓝牙配对后重连': 'No ATVV audio channel found. Pair the remote in system Bluetooth settings, '
                               'then reconnect.',
 '未发现遥控器广播；请靠近电脑并按键唤醒，首次使用需进入配对模式': 'Remote not found. Move it closer and press a button to wake it. First '
                                    'use requires pairing mode.',
 '未发现遥控器，继续扫描…': 'No remote found. Continuing scan…',
 '未完成的预览 · {source}': 'Unconfirmed preview · {source}',
 '未找到应用：{app}': 'Application not found: {app}',
 '未知按键手势': 'Unknown button gesture',
 '未知有道接口': 'Unknown Youdao service',
 '未知有道模型': 'Unknown Youdao model',
 '未知识别语言': 'Unknown recognition language',
 '未知语音模式': 'Unknown voice mode',
 '未识别到完整语句，请再试一次': 'No complete sentence recognized. Please try again.',
 '未识别到清晰语音，请再试一次': 'No clear speech recognized. Please try again.',
 '未连接': 'Disconnected',
 '本地识别已就绪 · 按住说话，松开输入': 'Local recognition ready · Hold to speak, release to insert',
 '本地识别语言': 'Recognition language',
 '本机离线 · SenseVoice': 'Local offline · SenseVoice',
 '本机离线识别': 'Local offline recognition',
 '本次识别失败：{error}': 'Recognition failed: {error}',
 '本次识别未最终确认，未自动输入；可手动复制预览或重新说话。': 'This result was not confirmed and was not inserted. Copy the preview '
                                  'manually or try again.',
 '查找': 'Find',
 '查看识别状态，轻松验证语音输入。': 'Check recognition status and test voice input.',
 '标准模型 · 优先断句与准确率': 'Standard model · Prioritize phrasing and accuracy',
 '模型文件尚未就绪': 'Model files are not ready',
 '模型文件已安装': 'Model files installed',
 '模型目录': 'Model directory',
 '正在上传到有道识别…': 'Uploading to Youdao for recognition…',
 '正在准备识别…': 'Preparing recognition…',
 '正在加载本地识别模型…': 'Loading local speech model…',
 '正在录音；请保持目标输入框的焦点。': 'Recording; keep the target text field focused.',
 '正在接收语音 · 松开结束': 'Receiving speech · Release to finish',
 '正在接收语音… 松开结束': 'Receiving speech… Release to finish',
 '正在识别…': 'Recognizing…',
 '正在连接有道…': 'Connecting to Youdao…',
 '此版本仅支持遥控器的 16 kHz 编码': "This version supports only the remote's 16 kHz codec",
 '测试与结果': 'Test & Results',
 '清空显示': 'Clear view',
 '点入下方，用遥控器说一句话，验证识别与输入。': 'Click below and speak using your remote to test recognition and insertion.',
 '点入目标文本框后说话，无需切回本窗口。': 'Focus the target text field and speak. You can leave this window in the background.',
 '点击动作编辑；修改后保存并连接。': 'Click an action to edit. Save & Connect to apply changes.',
 '点击后，在 3 秒内点入目标文本框': 'After clicking, focus your target text field within 3 seconds',
 '电源': 'Power',
 '界面语言未保存：{error}': 'Could not save display language: {error}',
 '目标焦点变化，已取消输入': 'Target focus changed; insertion canceled',
 '目标窗口或输入框已变化；结果已保留。请先点入目标输入框再说话。': 'The target window or field changed. Your result is preserved. Focus the '
                                    'target field before speaking.',
 '短语音接口需指定语言，例如 zh-CHS 或 en': 'Specify a language such as zh-CHS or en for short speech recognition',
 '短语音识别': 'Short speech recognition',
 '短语音识别：松开后上传': 'Short speech · Upload after release',
 '确认': 'OK',
 '确认 / Enter': 'Confirm / Enter',
 '离线模式不上传语音；首次使用需安装模型。单段最长 60 秒。': 'Offline mode never uploads audio. Install the model before first use. '
                                   'Each recording is limited to 60 seconds.',
 '等待遥控器；3 秒后重试': 'Waiting for the remote; retrying in 3 seconds',
 '签名校验失败，请检查应用 ID 和密钥': 'Signature verification failed. Check your App ID and secret.',
 '粘贴': 'Paste',
 '粤语': 'Cantonese',
 '系统时间不正确': 'Incorrect system time',
 '终端：Ctrl+Shift+V': 'Terminal: Ctrl+Shift+V',
 '结果已复制': 'Result copied',
 '缺少本地语音模型，请在语音设置中安装模型': 'Local speech model missing. Install it in voice settings.',
 '自动检测': 'Auto detect',
 '自定义快捷键': 'Custom shortcut',
 '英语': 'English',
 '菜单': 'Menu',
 '蓝牙地址格式应为 AA:BB:CC:DD:EE:FF': 'Bluetooth address must use the format AA:BB:CC:DD:EE:FF',
 '蓝牙遥控器': 'Bluetooth remote',
 '虚拟麦克风进程已退出': 'Virtual microphone process exited',
 '虚拟麦克风：Ubuntu Remote Microphone': 'Virtual microphone: Ubuntu Remote Microphone',
 '触发方式': 'Trigger mode',
 '让每一个按键，都更顺手。': 'Make every button work your way.',
 '识别不可用：{error}': 'Recognition unavailable: {error}',
 '识别会话闲置超时，本次未完成确认，请重新说话': 'Recognition session timed out before confirmation. Please speak again.',
 '识别后输入到原来的文本框（不按回车、不自动发送）': 'Insert into the original text field (never press Enter or send)',
 '识别完成': 'Recognition complete',
 '识别完成：音频 {audio:.1f} 秒，处理 {elapsed:.1f} 秒': 'Recognition complete: {audio:.1f} s audio, {elapsed:.1f} s '
                                             'processing',
 '识别尚未启动': 'Recognition has not started',
 '识别尚未就绪，本次仅输出麦克风音频': 'Recognition is not ready; only microphone audio is available for this recording',
 '识别已停止': 'Recognition stopped',
 '识别方式': 'Recognizer',
 '识别方式尚未启动': 'Recognizer has not started',
 '识别方式已更改 · 等待应用': 'Recognizer changed · Waiting to apply',
 '识别服务响应超时，请稍后重试': 'Recognition service timed out. Please try again later.',
 '识别结果': 'Recognition result',
 '识别队列已满，请等上一段完成后再说话': 'Recognition queue is full. Wait for the previous recording to finish.',
 '该接口不支持所选语言': 'This service does not support the selected language',
 '该模型不支持所选语言': 'This model does not support the selected language',
 '语言代码': 'Language code',
 '语音太短，请重新说话': 'Recording is too short. Please speak again.',
 '语音快捷键模式应为 hold 或 toggle': 'Voice shortcut mode must be hold or toggle',
 '语音设置': 'Voice settings',
 '语音超过 60 秒，已中止本段识别，请分段说话': 'Recording exceeded 60 seconds and was canceled. Please use shorter recordings.',
 '语音输入': 'Voice input',
 '请保存并连接以启动识别。': 'Click Save & Connect to start recognition.',
 '请在 3 秒内切换到目标文本框…': 'Focus the target text field within 3 seconds…',
 '请在有道控制台检查服务权限和请求状态': 'Check service permissions and request status in the Youdao console',
 '请在语音设置填写有道应用 ID 和应用密钥，再保存连接': 'Enter your Youdao App ID and secret in voice settings, then Save & Connect',
 '请按下所需组合键…': 'Press the shortcut now…',
 '请选择已安装的应用': 'Select an installed application',
 '调用过于频繁': 'Too many requests',
 '账号余额不足': 'Insufficient account balance',
 '输入失败：{error}': 'Insertion failed: {error}',
 '输入快捷键': 'Paste shortcut',
 '输入设备不可用：{error}': 'Input device unavailable: {error}',
 '运行记录': 'Activity log',
 '返回': 'Back',
 '连接与运行状态，清晰可查。': 'Connection details and activity, all in one place.',
 '连接中': 'Connecting',
 '连接外部应用': 'External application',
 '连接日志': 'Connection log',
 '连接未成功：{kind}: {error}': 'Connection unsuccessful: {kind}: {error}',
 '连接空闲超时，请检查网络后重新按住说话': 'Connection timed out. Check your network, then hold the voice button again.',
 '连接遥控器': 'Connect remote',
 '连接遥控器并协商语音…': 'Connecting to remote and negotiating audio…',
 '退出 / Escape': 'Escape',
 '退出 Remote Mic Linux': 'Quit Remote Mic Linux',
 '退出应用': 'Quit application',
 '退格': 'Backspace',
 '选择扫描到的遥控器': 'Select a discovered remote',
 '选择有道后，按语音键会通过加密连接上传音频，并消耗有道额度；需要应用开通所选服务。不会自动切换或重复请求其他收费服务。': 'In Youdao mode, pressing the voice button '
                                                                'uploads audio over an encrypted connection '
                                                                'and uses your Youdao quota. Enable the '
                                                                'selected service for your application. '
                                                                'Other paid services are never selected or '
                                                                'retried automatically.',
 '通知栏当前不可用，请检查 Ubuntu AppIndicators 扩展。可使用“退出应用”结束程序。': "The tray is unavailable. Check your desktop's "
                                                        'AppIndicator support. Use Quit application to exit.',
 '通知栏组件不可用；请安装 gir1.2-ayatanaappindicator3-0.1。关闭窗口将退出。': 'Tray support is unavailable. Install '
                                                          'gir1.2-ayatanaappindicator3-0.1. Closing the '
                                                          'window will quit the application.',
 '遥控器切换到了不支持的音频编码': 'The remote switched to an unsupported audio codec',
 '遥控器型号：{model}': 'Remote model: {model}',
 '遥控器按键缓冲溢出，正在重新同步': 'Remote button buffer overflow; resynchronizing',
 '遥控器语音安全测试框': 'Safe remote voice input test field',
 '遥控器语音结束': 'Remote microphone audio ended',
 '配置有误，请查看日志': 'Configuration error; check the logs',
 '配置未保存：{error}': 'Configuration was not saved: {error}',
 '重做': 'Redo',
 '长按': 'Hold',
 '需要检查': 'Check required',
 '静音': 'Mute',
 '韩语': 'Korean',
 '音量 +': 'Volume +',
 '音量 −': 'Volume −',
 '音量增加': 'Volume up',
 '音量降低': 'Volume down',
 '音频尚未发送完毕，有道已结束识别': 'Youdao ended recognition before all audio was sent',
 '＋ 添加': '＋ Add'}


def normalize_locale(locale):
    return "zh_CN" if locale == "zh" else locale if locale in LOCALES else DEFAULT_LOCALE


def load_locale(path=None):
    try:
        value = json.loads(Path(path or PREFERENCES).read_text())
        return normalize_locale(value.get("language"))
    except (OSError, ValueError, AttributeError, TypeError):
        return DEFAULT_LOCALE


def save_locale(locale, path=None):
    target = Path(path or PREFERENCES)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=".ui-")
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump({"language": normalize_locale(locale)}, output)
            output.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass(frozen=True)
class Message:
    key: str
    parameters: tuple = ()

    def __str__(self):
        return render(self, DEFAULT_LOCALE)

    def __contains__(self, value):
        # Keep canonical diagnostics readable to command-line clients and tests.
        return value in str(self)


def msg(template, **parameters):
    return Message(template, tuple(parameters.items()))


def message_key(value):
    return value.key if isinstance(value, Message) else str(value)


def error_message(error):
    # Preserve a translatable internal error without exposing request details.
    return error.args[0] if error.args and isinstance(error.args[0], Message) else msg(str(error))


def render(value, locale=DEFAULT_LOCALE):
    locale = normalize_locale(locale)
    if isinstance(value, BaseException):
        value = error_message(value)
    key = message_key(value)
    template = ENGLISH.get(key, key) if locale == "en" else key
    if isinstance(value, Message) and value.parameters:
        parameters = {name: render(item, locale) if isinstance(item, (Message, BaseException)) else item
                      for name, item in value.parameters}
        return template.format(**parameters)
    return template


class Translator:
    """An explicit registry of translatable widget properties, with no GTK patching."""
    def __init__(self, locale=DEFAULT_LOCALE):
        self.locale = normalize_locale(locale)
        self.bindings = {}
        self.combos = []
        self.listeners = []

    def text(self, value):
        return render(value, self.locale)

    def bind(self, widget, method, value):
        self.bindings[(id(widget), method)] = (widget, method, value)
        getattr(widget, method)(self.text(value))
        return widget

    def label(self, widget, value):
        return self.bind(widget, "set_label", value)

    def combo(self, widget, items, active):
        items = tuple(items)
        for key, value in items:
            widget.append(key, self.text(value))
        widget.set_active_id(active)
        self.combos.append((widget, items))
        return widget

    def forget(self, widgets):
        identities = {id(widget) for widget in widgets}
        self.bindings = {key: value for key, value in self.bindings.items() if key[0] not in identities}
        self.combos = [(widget, items) for widget, items in self.combos if id(widget) not in identities]

    def set_locale(self, locale):
        self.locale = normalize_locale(locale)
        for widget, method, value in tuple(self.bindings.values()):
            getattr(widget, method)(self.text(value))
        for widget, items in self.combos:
            # Update display cells only. Active IDs and editor values stay intact.
            model = widget.get_model()
            for row, (_, value) in zip(model, items):
                row[0] = self.text(value)
        for callback in tuple(self.listeners):
            callback()
