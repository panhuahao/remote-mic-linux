# 开发与贡献

先阅读 README.md、SOURCES.md 和 LICENSE.md。代码采用 GPL-3.0-only，提交衍生代码应保留上游归属和许可说明。

## 开发环境

在 Ubuntu 图形桌面安装 README 中的系统依赖，再执行：

    ./install.sh
    .venv/bin/python -m unittest discover -s tests -v

自动检查使用模拟输入设备、本地 WebSocket 和临时凭据文件，不需要遥控器，不调用真实有道服务。带界面的集成测试需真实用户桌面会话及 /dev/uinput 权限，见 docs/TESTING.md。GitHub Actions 仅运行自动检查，不代表蓝牙硬件验收。

## 提交内容

- 将改动和验证方式写入更新说明，区分模拟测试与真机测试。
- 新设备报告提供型号、固件、Ubuntu 版本及 X11/Wayland 类型；不要公开蓝牙地址、密钥或个人录音。
- 不把 .venv、模型、日志、凭据或真实用户配置加入版本控制。
- 云接口修改优先使用模拟通信；真实收费测试必须由账号持有人明确授权。
- 自动输入不得自动按 Enter；应保留断连取消、过期结果取消及目标焦点校验。

## 打包

    python3 scripts/build_release.py
    cd dist
    sha256sum -c SHA256SUMS

打包脚本只包含显式列出的源码和文档。新增公共文件类型时同步维护脚本允许列表。源码归档不包含 Python 环境或模型。AppImage 单独捆绑运行环境，不含模型或私有数据；构建方法见 RELEASE.md。构建脚本本身不上传 GitHub。
