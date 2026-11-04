#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
python3 -c 'import gi; gi.require_version("Gtk", "3.0")' || {
  echo '缺少 GTK：请安装 python3-gi gir1.2-gtk-3.0 python3-venv python3-dev build-essential' >&2
  exit 1
}
command -v pw-cat >/dev/null || { echo '请安装 pipewire-bin' >&2; exit 1; }
command -v wl-copy >/dev/null && command -v wl-paste >/dev/null || { echo '请安装 wl-clipboard' >&2; exit 1; }
python3 -c 'import gi; gi.require_version("Atspi", "2.0")' || { echo '请安装 gir1.2-atspi-2.0' >&2; exit 1; }
python3 -c 'import gi; gi.require_version("AyatanaAppIndicator3", "0.1")' || { echo '请安装 gir1.2-ayatanaappindicator3-0.1（通知栏常驻）' >&2; exit 1; }
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python install_desktop.py
