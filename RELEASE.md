# Remote Mic Linux 发布说明

当前应用版本：**0.5.0**。构建基线：**Ubuntu 24.04 x86_64 / Python 3.12 / glibc 2.39**。提供 AppImage、DEB 和源码归档。构建时检查实际 ELF 符号需求，拒绝带入高于 glibc 2.39 的依赖；桌面与硬件验证范围见 [docs/TESTING.md](docs/TESTING.md)。

## 发布附件

| 文件 | 用途 |
| --- | --- |
| Remote-Mic-Linux-0.5.0-x86_64.AppImage | 免安装应用，包含私有 Python、GTK 和识别运行库 |
| remote-mic-linux_0.5.0_amd64.deb | Ubuntu 安装包，安装启动器、应用列表入口、图标和私有运行库 |
| remote-mic-linux-0.5.0-source.tar.gz / .zip | 源码、构建脚本、测试、中英文文档和截图 |
| SHA256SUMS | 上述四个附件的 SHA256 |

安装包不包含语音模型、设备地址、凭据、用户设置、日志或录音。DEB 与 AppImage 使用同一个 AppDir，不修改系统 Python。宿主仍提供 glibc、图形驱动、BlueZ、PipeWire、AT-SPI、XWayland 和设备权限。`pw-cat` 使用宿主版本并恢复宿主环境，避免混用不同版本的 PipeWire 插件。

## Ubuntu 24 构建

推荐使用 Docker 构建，避免在较新系统误打包较新的运行库。Docker 构建上下文由 `.dockerignore` 限制为依赖文件和 Dockerfile；应用构建容器只收到源码允许列表中的文件，不挂载用户配置、模型、真实设备或桌面会话。

取得 AppImage/type2-runtime 官方 `runtime-x86_64` 及许可证。当前固定 runtime 的 SHA256 为：

    617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46

```sh
./scripts/build_ubuntu24.sh /path/to/runtime-x86_64 /path/to/runtime-LICENSE
```

构建过程先创建 Ubuntu 24.04 构建镜像，再在独立源码目录中运行测试、打包 AppImage 与 DEB，并生成源码包和校验值。可用 `REMOTE_MIC_BUILD_IMAGE` 指定构建镜像名称，`REMOTE_MIC_BASE_IMAGE` 指定已核验的 Ubuntu 24.04 镜像引用；默认分别为 `remote-mic-linux-build:ubuntu24` 与 `ubuntu:24.04`。

网络受限时，可通过 `REMOTE_MIC_APT_MIRROR` 指定 Ubuntu 软件源镜像（仍校验 Ubuntu 签名），通过 `REMOTE_MIC_PIP_PROXY` 指定下载公开 Python 依赖的代理。`REMOTE_MIC_BUILD_NETWORK` 可指定镜像构建阶段的 Docker 网络；本地代理可能需要 `host`。这些选项仅用于准备依赖镜像，后续应用打包容器始终使用 `--network=none`。

已在 Ubuntu 24.04 构建环境内准备好依赖时，也可以直接运行：

```sh
python3 scripts/build_appimage.py --runtime /path/to/runtime-x86_64 --runtime-license /path/to/runtime-LICENSE
python3 scripts/build_deb.py --appdir build/RemoteMicLinux.AppDir
python3 scripts/build_release.py
(cd dist && sha256sum -c SHA256SUMS)
```

直接构建要求 Python 3.12，且构建机 glibc 不高于 2.39。构建脚本不能在本机 Ubuntu 26 / Python 3.14 环境直接代替容器运行。

GTK 输入法模块、GdkPixbuf loaders、GIO 模块、图标主题和 schemas 随运行库提供；含绝对路径的模块缓存会在启动时重建，并在退出时清理。启动外部应用与宿主音频工具时会恢复相应宿主环境。

构建信息、实际 ELF 检查结果、Python 依赖版本和系统库版权资料保存在 AppDir 的 `usr/share/doc/remote-mic-linux/`。Python 依赖保留各自包元数据及许可证。模型遵循单独许可，不随安装包分发。

## 安装与迁移

```sh
sudo apt install ./remote-mic-linux_0.5.0_amd64.deb
remote-mic-linux --version
remote-mic-linux --self-test
```

DEB 安装到 `/usr/lib/remote-mic-linux`，命令入口为 `/usr/bin/remote-mic-linux`。安装过程不联网执行 pip、不下载模型、不启动 GUI，也不批量放开输入设备权限。删除软件包不删除用户目录中的设置和模型。

```sh
sudo apt remove remote-mic-linux
```

已有 AppImage 用户若执行过 `--install-desktop`，用户级 `~/.local/share/applications/io.github.panhuahao.RemoteMicLinux.desktop` 可能仍指向旧 AppImage，并覆盖 DEB 的系统入口。迁移时先退出旧实例，确认不再需要旧入口后将该用户级文件移走，或直接使用 `remote-mic-linux` 命令启动。安装器不擅自删除用户文件。

AppImage 无需安装；无法使用 FUSE 的环境可执行：

```sh
./dist/Remote-Mic-Linux-0.5.0-x86_64.AppImage --appimage-extract-and-run --self-test
```

## 验证与发布

1. 对齐源码版本、README、CHANGELOG、标签和附件名称；界面截图使用空凭据与空设备地址。
2. 在 Ubuntu 24 环境检查 ELF、依赖导入、普通用户图形界面和本地推理；分别验证 DEB 安装、同版本重装、卸载与用户数据保留。当前生命周期脚本不测试跨版本升级，需另行验证。
3. 在 Ubuntu 26 桌面验证新 AppImage；真实遥控器、跨应用输入和其他发行版验证单独记录。容器中的 Xvfb 测试不等同于真实蓝牙或 Wayland 桌面验收。
4. 检查源码归档与两种安装包内容，排除私有数据，核对 SHA256。
5. 将核验后的源码、版本标签和对应附件一起发布；已发布附件不静默覆盖。

源代码归档与校验文件由显式允许列表生成。新增公共脚本、构建文件或资源时同步维护 `scripts/build_release.py`。GitHub CI 的源码检查不替代安装包和实物验证。
