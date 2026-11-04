# 验证说明

## 自动检查

    .venv/bin/python -m unittest discover -s tests -v

2026-11-05，v0.3.0 本机 52 项通过，覆盖 ATVV、按键释放、手势、识别队列、过期结果、有道签名及模拟通信、凭据权限、文本输入取消、焦点事件顺序和 Wayland/XWayland 判断。测试不调用真实收费接口。

## 受控跨应用验证

在已登录的 GNOME 桌面会话运行，需 GTK、AT-SPI、XWayland 和 /dev/uinput 访问权限。测试会弹出自己的独立输入窗口；等待约 8 秒，期间不要切换窗口：

    .venv/bin/python scripts/check_cross_app.py --backend x11
    .venv/bin/python scripts/check_cross_app.py --backend wayland

测试先核对目标属于自己创建的子进程，再模拟“语音开始”和“最终结果”事件。它使用固定文本，不录音，不连接遥控器或有道，不读取其他应用文本。测试设置位于临时目录。成功时输出 passed: true 和字符数 8；不自动按 Enter。

本机 0.2.1 和 0.3.0 均在独立 X11 和原生 Wayland GTK 输入框通过。0.3.0 验证时桥接窗口在后台，两个目标均收到 8 个字符。该结果验证焦点、剪贴板与虚拟按键链路，不等于所有应用兼容。

## 真实遥控器验收

1. 启动程序并连接遥控器，选择本地或已配置的有道模式。
2. 在另一个应用中点入实际要输入的文本框，保持这个窗口和输入框处于焦点。
3. 不切回桥接程序；按住遥控器语音键说话，松开后等待文字出现。
4. 确认文字只出现一次，没有自动回车或发送。
5. 另测识别期间切换到不同窗口、停止连接，确认取消输入且结果仍可复制。

先前用户已确认本地与有道均能将遥控器识别结果输入程序内安全测试框。修复版在用户日常应用中的完整遥控器验收尚待确认，应与受控窗口测试分开记录。

## 已知边界

- 仅遥控器 2 / RC001 有实物测试，2 Pro / RC003 待实测。
- 不提供无障碍字段信息的应用只能按窗口校验，不能保证发现同窗口内的字段变化。
- 焦点与密码框识别依赖应用公开的无障碍信息；无法识别所有密码框。
- 使用 Ctrl+V，终端需按 UI 设置选择 Ctrl+Shift+V。自定义粘贴快捷键或禁用粘贴的输入框可能不支持。
- GTK 剪贴板桥接在本机 X11/XWayland 程序进程中验证；其他桌面环境仍需验证。

## v0.3.0 通知栏与桌面集成（2026-11-05）

- 实际 StatusNotifierWatcher 已接收本应用指示器；关闭事件隐藏窗口，应用继续运行且连接 generation 不变。
- 收起后重新运行启动命令，确认进程 PID 不变、原窗口恢复；没有再次连接遥控器。
- WM_CLASS、_GTK_APPLICATION_ID 均为 io.github.panhuahao.RemoteMicLinux；窗口名为 Remote Mic Linux，与 desktop 文件身份一致。
- 图标导出为 SVG、64/256/512 PNG；菜单和录音状态使用专用小尺寸遥控器图标。
- 四个页面完成窗口布局检查；README 使用空地址、无账号凭据的隔离配置截图。

## v0.3.0 有道结束消息修复

保留用户选择的实时短语音接口。公开 5.592 秒样例实际复现最终片段后 closeCode=0 / errorCode=304 的结束响应；修复后获得一次最终 transcript 和“有道识别完成”。此诊断不保存用户录音。

新增回归覆盖：partial 不算完成、最终片段后正常关闭只提交一次、仅 partial 后 304 不提交、正常关闭标记不掩盖认证错误。单元测试使用本地模拟通信，不消耗云额度。

## AppImage 验证方法

识别来源 UI 回归可在图形会话单独运行：

    .venv/bin/python scripts/check_voice_ui.py

使用临时空凭据配置和固定文本，关闭自动粘贴，不启动遥控器或真实识别服务。检查切换时旧连接 generation 失效、历史结果保留来源、新设置待应用、迟到的有道成功被忽略、本地结果标注正确。本机五项状态检查均通过。

~~~sh
./dist/Remote-Mic-Linux-0.3.0-x86_64.AppImage --version
./dist/Remote-Mic-Linux-0.3.0-x86_64.AppImage --self-test
./dist/Remote-Mic-Linux-0.3.0-x86_64.AppImage --appimage-extract-and-run --self-test
~~~

检查 imports 的路径全部指向包内 site-packages。自测只加载依赖，不连接遥控器、不调用收费接口。实际桌面测试仍需要宿主蓝牙、PipeWire、AT-SPI 与设备访问权限。AppImage 是本机目标系统构建，尚未在干净的新装系统或其他发行版验证。

发布前还使用 AppImage 同一 AppDir 内的 Python/GTK/识别运行库验证：公开中文样例本地识别得到 14 个字符，独立 X11 和 Wayland 输入框各收到 8 个固定测试字符。FUSE 运行与 --appimage-extract-and-run 的依赖自测均通过；模块路径均位于包内。没有为此次界面与打包验证再次调用收费识别接口。
