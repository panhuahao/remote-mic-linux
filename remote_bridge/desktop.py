# SPDX-License-Identifier: GPL-3.0-only
"""Launch host applications without leaking the AppImage Python/GTK runtime."""
import os
from gi.repository import Gio, Gdk
from .runtime_environment import host_environment

def launch_context():
    context=Gdk.Display.get_default().get_app_launch_context()
    original=dict(os.environ)
    environment=host_environment(original)
    for name in original.keys()-environment.keys():
        context.unsetenv(name)
    for name,value in environment.items():
        if original.get(name)!=value:
            context.setenv(name,value)
    return context

def open_uri(uri):
    Gio.AppInfo.launch_default_for_uri(uri,launch_context())
