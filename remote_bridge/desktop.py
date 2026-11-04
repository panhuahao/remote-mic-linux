# SPDX-License-Identifier: GPL-3.0-only
"""Launch host applications without leaking the AppImage Python/GTK runtime."""
import os
from gi.repository import Gio, Gdk

def launch_context():
    context=Gdk.Display.get_default().get_app_launch_context()
    if os.environ.get('REMOTE_MIC_BUNDLE')=='1':
        for name in ('PYTHONHOME','PYTHONPATH','PYTHONNOUSERSITE','PYTHONDONTWRITEBYTECODE',
                     'LD_LIBRARY_PATH','GI_TYPELIB_PATH','GDK_PIXBUF_MODULE_FILE','GDK_BACKEND',
                     'APPDIR','APPIMAGE','OWD','REMOTE_MIC_BUNDLE'):
            context.unsetenv(name)
        context.setenv('PATH',os.environ['REMOTE_MIC_HOST_PATH'])
        context.unsetenv('REMOTE_MIC_HOST_PATH')
    return context

def open_uri(uri):
    Gio.AppInfo.launch_default_for_uri(uri,launch_context())
