# SPDX-License-Identifier: GPL-3.0-only
"""Install current-user launchers and the original Remote Mic Linux icon."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
from remote_bridge.identity import APP_ID, APP_NAME, ICON_NAME

root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--appimage',type=Path,help='Use a built AppImage instead of the source runner')
args=parser.parse_args()
command=str((args.appimage or root/'run.sh').resolve())
if not Path(command).is_file():raise SystemExit('Launcher target does not exist')
for character in ('\\','"','$',chr(96)):
    command=command.replace(character,'\\'+character)
command=command.replace('%','%%')
data=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))
directory=data/'applications';directory.mkdir(parents=True,exist_ok=True)
icon_theme=data/'icons/hicolor'
for size,asset in ((64,'remote-mic-linux-64.png'),(256,'remote-mic-linux-256.png'),(512,'remote-mic-linux.png')):
    icons=icon_theme/(str(size)+'x'+str(size))/'apps';icons.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/'assets'/asset,icons/(ICON_NAME+'.png'))
icons=icon_theme/'scalable/apps';icons.mkdir(parents=True,exist_ok=True)
shutil.copy2(root/'assets/remote-mic-linux.svg',icons/(ICON_NAME+'.svg'))
body='\n'.join([
    '[Desktop Entry]','Type=Application','Name='+APP_NAME,
    'Comment=蓝牙遥控器按键映射与语音输入（非官方 Linux 适配）',
    'Exec="'+command+'" --autostart','Icon=remote-mic-linux','Terminal=false',
    'Categories=AudioVideo;Audio;','StartupWMClass='+APP_ID,
    'Keywords=remote;microphone;dictation;bluetooth;遥控器;语音;',''])
launcher_directory=args.appimage.resolve().parent if os.environ.get('REMOTE_MIC_BUNDLE')=='1' else root
for destination in [directory/(APP_ID+'.desktop'),launcher_directory/'Remote Mic Linux.desktop']:
    destination.write_text(body);destination.chmod(0o755)
old_ids=('ubuntu-remote-bridge.desktop','remote-mic-linux.desktop')
for old_id in old_ids:
    old=directory/old_id
    if old.exists() and any(name in old.read_text() for name in ('Name=Ubuntu 遥控器桥接','Name=Remote Mic Linux')):old.unlink()
old=root/'启动遥控器桥接.desktop'
if old.exists() and 'Name=Ubuntu 遥控器桥接' in old.read_text():old.unlink()
if shutil.which('update-desktop-database'):
    subprocess.run(['update-desktop-database',str(directory)],check=False)
if shutil.which('gtk-update-icon-cache'):
    subprocess.run(['gtk-update-icon-cache','-f','-t',str(icon_theme)],check=False,capture_output=True)
try:
    from gi.repository import Gio
    if Gio.SettingsSchemaSource.get_default().lookup('org.gnome.shell',True):
        settings=Gio.Settings.new('org.gnome.shell')
        favorites=settings.get_strv('favorite-apps')
        updated=[APP_ID+'.desktop' if item in old_ids else item for item in favorites]
        if updated!=favorites:settings.set_strv('favorite-apps',list(dict.fromkeys(updated)));Gio.Settings.sync()
except (ImportError,AttributeError):pass
print('Installed Remote Mic Linux launchers')
