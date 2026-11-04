# 来源与第三方声明

## SayAll

- 官网：https://sayall.app/
- 公开仓库：https://github.com/HD838A/remote-mic-app
- 本次读取的固定提交：96b9df005707c1268e47316e1ba46aed0ef42c63
- Copyright (C) 2026 SayAll contributors
- 软件代码许可：GPL-3.0-only；保留完整 LICENSE.md。

remote_bridge/protocol.py 将以下公开文件中的协议常量、能力解析、IMA ADPCM 解码、分帧与会话处理适配为 Python：

- Sources/RemoteMic/ATVVProtocol.swift
- Sources/RemoteMic/XiaomiBluetoothBridge.swift
- Tests/RemoteMicTests/ATVVProtocolTests.swift（协议测试向量）

Linux 版本重新实现 BlueZ 接入、PipeWire 虚拟音源、evdev/uinput 按键映射和 GTK 界面。改动日期：2026-11-04。没有使用官网设计素材、Logo、App Icon 或私有模块。

上游的版权说明还列出其参考项目 xxb26553663-star/remote-bridge-hub（GPL-3.0-only），参考提交 8a93f321ac71a602300c6cd77f7256fa4b63068e；此处保留该来源信息。本适配未引入该项目的 Windows 驱动、Frida 或第三方二进制组件。

## Python 运行依赖

| 依赖 | 本机版本 | 包声明许可 |
| --- | --- | --- |
| bleak | 3.0.2 | MIT |
| dbus-fast | 5.2.0 | MIT |
| evdev | 2.0.0 | BSD-3-Clause |

以上许可信息来自本机安装包元数据；完整依赖许可保留在 .venv 中的各自 dist-info 目录。系统 GTK/PyGObject、BlueZ、PipeWire 由 Ubuntu 安装环境提供，适用各自许可。

## 0.2.0 语音识别与输入（2026-11-04）

- SenseVoice 原始模型：https://huggingface.co/FunAudioLLM/SenseVoiceSmall （独立 model-license）。
- ONNX 发布资源：https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17
- 推理运行时：https://github.com/k2-fsa/sherpa-onnx ，本机使用 2.0.1。
- 模型 model.int8.onnx：239233841 字节；SHA256 c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51。
- tokens.txt：315894 字节；Git blob 2cfc92fc2ff26aaa690b7c01fd96b41109413881。
- 本机通过 hf-mirror.com 获取同一发布资源，模型 SHA256 校验通过。测试音频采用同仓库 test_wavs/zh.wav。
- 有道大模型实时语音识别：https://ai.youdao.com/DOCSIRMA/html/tts/api/dmxssyysb/
- 有道短语音识别：https://ai.youdao.com/DOCSIRMA/html/tts/api/dyysb/index.html
- 有道实时短语音识别：https://ai.youdao.com/DOCSIRMA/html/tts/api/ssdyysb/index.html
- 有道普通实时语音识别：https://ai.youdao.com/DOCSIRMA/html/tts/api/ssyysb/index.html

有道接口为按官方文档独立实现，不包含供应商密钥。大模型签名遵循文档 v4，短语音按参数表使用 v3（该页旧示例仍出现 v2，以现行参数表为实现依据）。用户账号的大模型标准版、流式 WAV、结束响应已通过真实公开样例联调；实时短语音也已通过公开样例验证；普通实时与非流式短语音仍待真实接口验证。实测发现结束帧需要保留官方示例冒号后的空格，已加回归检查。

## 0.2.1 桌面输入适配（2026-11-04）

GTK/AT-SPI 用于剪贴板所有权与公开活动窗口元数据，libX11 只查询窗口标识，不读取目标应用文本。新增实现位于 clipboard.py、window_focus.py 和 focus.py，按 GPL-3.0-only 分发。源码发布包不捆绑系统库、Python 依赖二进制或模型。

## 0.3.0 界面、图标、通知栏与打包（2026-11-05）

- 应用彩色图标及通知栏遥控器图标为本项目原创 SVG，与本项目代码一同按 GPL-3.0-only 提供。造型参考银色直边圆角遥控器的一般工业设计风格，没有使用 Apple 或 SayAll 的 Logo/图标文件，不表示对应品牌授权或硬件兼容。
- GitHub 链接使用 primer/octicons 的 mark-github-16.svg，仅用于指向本项目仓库；来源 https://github.com/primer/octicons/blob/main/icons/mark-github-16.svg 。保留 MIT 许可于 assets/github-icon-LICENSE.txt，显示颜色和 PNG 导出为本项目修改；GitHub 商标权不由图标源码许可替代。
- 通知栏使用 Ayatana AppIndicator / StatusNotifier 协议和宿主 Ubuntu AppIndicators 扩展。打包包含所需运行库和 typelibs，宿主提供桌面扩展与会话总线。
- AppImage type2 runtime 来源 https://github.com/AppImage/type2-runtime ，下载资源 https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64 。本次采用的文件 SHA256 为 617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46。原许可证随包保存。
- AppImage 捆绑 Python、PyGObject/GTK、pycairo、numpy、sherpa-onnx、bleak、dbus-fast、evdev、websockets、typing_extensions 及必要动态库、pw-cat 和 wl-clipboard。各自保留原许可；打包脚本记录准确版本、系统包名、版权文件和 Python dist-info 元数据。应用许可证不替代第三方许可证。
- 上游功能对照另外固定至 03e96e92c9962acb8a7ef497db19089be46d97db；其中 SayAllAI、宏和按键方案存在可选私有组件入口，不包含在本项目中。具体差异见 docs/FEATURE_COMPARISON.md。
