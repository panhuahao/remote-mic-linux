# Remote Mic Linux 发布说明

当前版本：**0.3.0**。目标：**Ubuntu 26.04 x86_64**。仓库：**panhuahao/remote-mic-linux，私有**。GitHub Releases 使用预发布标记；无需将仓库公开即可供有权限的账号下载。

## 发布附件

| 文件 | 用途 |
| --- | --- |
| Remote-Mic-Linux-0.3.0-x86_64.AppImage | 可直接执行的成品应用，包含 Python/GTK/识别运行库 |
| remote-mic-linux-0.3.0-source.tar.gz | 源码、构建脚本、测试、文档、图标、脱敏截图 |
| remote-mic-linux-0.3.0-source.zip | 同一源码的 ZIP 格式 |
| SHA256SUMS | 三个附件的 SHA256 |

模型、凭据、设置、设备地址、用户录音、日志和 .venv 不进入源码包。AppImage 包含运行依赖及各自许可声明，不包含用户数据或语音模型。

## 本地目录

remote_bridge/ 为代码，assets/ 为原创图标、GitHub 标识及脱敏截图，tests/ 与 scripts/ 为测试和构建工具，docs/ 为测试和功能对照。dist/ 存放成品，build/ 为打包中间目录，local/ 为仅本机文件。这三个目录及 .venv/ 不提交 Git。

项目根目录的 Remote Mic Linux.AppImage 指向 dist 中本版成品；Remote Mic Linux.desktop 是当前机器的启动入口，均不提交 Git。用户配置与模型继续使用旧的 ubuntu-remote-bridge 私有路径以保持兼容。

## 构建 AppImage

在 Ubuntu 26.04 x86_64 安装应用依赖及 squashfs-tools。构建时使用项目 .venv 的 Python 3.14；当前配方不用于生成旧 Ubuntu 兼容包。

取得 AppImage/type2-runtime 的官方 runtime-x86_64 和许可证，放在本机 local/ 或其他不提交的目录。构建脚本校验固定 SHA256：

    617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46

~~~sh
.venv/bin/python scripts/build_appimage.py --runtime /path/to/runtime-x86_64 --runtime-license /path/to/runtime-LICENSE
./dist/Remote-Mic-Linux-0.3.0-x86_64.AppImage --version
./dist/Remote-Mic-Linux-0.3.0-x86_64.AppImage --self-test
./dist/Remote-Mic-Linux-0.3.0-x86_64.AppImage --appimage-extract-and-run --self-test
python3 scripts/build_release.py
(cd dist && sha256sum -c SHA256SUMS)
~~~

--self-test 不连接设备，不调用有道；输出导入位置，用于确认依赖来自包内。AppImage 保留宿主 glibc、图形桌面及蓝牙/音频服务。运行库版权、版本与系统包清单保存在包内 usr/share/doc/remote-mic-linux/，Python 依赖的 dist-info 许可也一并保留。

源码脚本采用文件允许列表和固定归档元数据；新增公开资源时同步维护。它会为本版 AppImage 与源码包一起生成校验文件。GitHub CI 只执行单元测试和源码构建，AppImage 当前在本机目标系统构建。

## 发布核对

1. 统一 remote_bridge/__init__.py、README、CHANGELOG、Release 标记和附件版本；截图重新从无凭据配置拍摄。
2. 通过单元、通知栏/单实例、独立 X11/Wayland 输入及 AppImage 自测；硬件验证单独记录。
3. 审查 Git 暂存、源码归档和 AppImage 内容，排除凭据、真实设备地址、录音、日志和模型。
4. 只推送已核验为 PRIVATE 的 panhuahao/remote-mic-linux；创建 v0.3.0 预发布并上传上述四个附件。
5. 重新核实仓库仍为私有、附件名称/大小/校验值正确。不要执行仓库公开操作。
