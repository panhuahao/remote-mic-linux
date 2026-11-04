#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
# Keep clipboard ownership available while the GUI is in the background.
# Native Wayland targets still receive the compositor's clipboard bridge.
export GDK_BACKEND="${GDK_BACKEND:-x11}"
if [ ! -x .venv/bin/python ]; then
  echo '请先运行 ./install.sh' >&2
  exit 1
fi
exec .venv/bin/python -m remote_bridge "$@"
