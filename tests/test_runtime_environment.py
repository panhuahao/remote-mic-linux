# SPDX-License-Identifier: GPL-3.0-only
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from remote_bridge.runtime_environment import host_environment


class RuntimeEnvironmentTests(unittest.TestCase):
    def environment(self):
        return {
            "REMOTE_MIC_BUNDLE": "1", "APPDIR": "/bundle", "APPIMAGE": "/app.AppImage",
            "OWD": "/working", "PATH": "/bundle/usr/bin:/usr/bin",
            "REMOTE_MIC_HOST_PATH": "/usr/local/bin:/usr/bin",
            "XDG_DATA_DIRS": "/bundle/usr/share:/host/share",
            "REMOTE_MIC_HOST_XDG_DATA_DIRS": "/host/share",
            "GDK_BACKEND": "x11", "REMOTE_MIC_HOST_GDK_BACKEND": "wayland,x11",
            "PYTHONHOME": "/bundle/usr", "PYTHONPATH": "/bundle/python",
            "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
            "LD_LIBRARY_PATH": "/bundle/lib", "GI_TYPELIB_PATH": "/bundle/typelibs",
            "GDK_PIXBUF_MODULE_FILE": "/bundle/pixbuf.cache",
            "GTK_IM_MODULE_FILE": "/bundle/immodules.cache", "GIO_MODULE_DIR": "/bundle/gio",
            "REMOTE_MIC_HOST_GTK_MODULES": "canberra-gtk-module:appmenu-gtk-module",
            "REMOTE_MIC_HOST_GTK_PATH": "/host/gtk/modules",
            "REMOTE_MIC_HOST_GIO_EXTRA_MODULES": "",
            "HOME": "/home/person", "DISPLAY": ":7", "WAYLAND_DISPLAY": "wayland-0",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
            "XDG_RUNTIME_DIR": "/run/user/1000", "PIPEWIRE_REMOTE": "custom-pipewire",
            "HTTPS_PROXY": "http://proxy.example:8080", "EXAMPLE_USER_SECRET": "opaque",
        }

    def test_host_runtime_restores_paths_and_preserves_session_and_user_values(self):
        environment = self.environment()
        before = dict(environment)
        result = host_environment(environment)
        expected = {key: environment[key] for key in (
            "HOME", "DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS",
            "XDG_RUNTIME_DIR", "PIPEWIRE_REMOTE", "HTTPS_PROXY", "EXAMPLE_USER_SECRET")}
        expected.update(PATH="/usr/local/bin:/usr/bin", XDG_DATA_DIRS="/host/share",
                        GDK_BACKEND="wayland,x11", GTK_MODULES="canberra-gtk-module:appmenu-gtk-module",
                        GTK_PATH="/host/gtk/modules", GIO_EXTRA_MODULES="")
        self.assertEqual(result, expected)
        self.assertEqual(environment, before)

    def test_unset_optional_host_variables_do_not_inherit_bundle_values(self):
        environment = self.environment()
        environment["REMOTE_MIC_HOST_XDG_DATA_DIRS"] = ""
        environment["REMOTE_MIC_HOST_GDK_BACKEND"] = ""
        result = host_environment(environment)
        self.assertNotIn("XDG_DATA_DIRS", result)
        self.assertNotIn("GDK_BACKEND", result)

    def test_missing_path_backup_uses_system_lookup_not_private_bin(self):
        environment = self.environment()
        del environment["REMOTE_MIC_HOST_PATH"]
        self.assertEqual(host_environment(environment)["PATH"], os.defpath)

    def test_host_modules_preserve_unset_empty_and_nonempty_values(self):
        for name in ("GTK_MODULES", "GTK_PATH", "GIO_EXTRA_MODULES"):
            backup = "REMOTE_MIC_HOST_" + name
            for value in (None, "", "/host/module path"):
                with self.subTest(name=name, value=value):
                    environment = self.environment()
                    # Do not trust leftover module settings in the bundle.
                    environment[name] = "/bundle/module"
                    environment.pop(backup, None)
                    if value is not None:
                        environment[backup] = value
                    result = host_environment(environment)
                    if value is None:
                        self.assertNotIn(name, result)
                    else:
                        self.assertEqual(result[name], value)
                    self.assertNotIn(backup, result)
                    self.assertEqual(environment[name], "/bundle/module")

    def test_source_mode_leaves_runtime_customization_untouched(self):
        environment = self.environment()
        del environment["REMOTE_MIC_BUNDLE"]
        result = host_environment(environment)
        self.assertEqual(result, environment)
        self.assertIsNot(result, environment)

    def test_desktop_context_receives_only_environment_changes(self):
        import gi
        gi.require_version("Gdk", "3.0")
        from remote_bridge import desktop
        environment = self.environment()
        context = Mock()
        display = Mock()
        display.get_app_launch_context.return_value = context
        with patch.dict(os.environ, environment, clear=True), \
             patch.object(desktop.Gdk.Display, "get_default", return_value=display):
            self.assertIs(desktop.launch_context(), context)
        applied = dict(environment)
        for call in context.unsetenv.call_args_list:
            applied.pop(call.args[0])
        for call in context.setenv.call_args_list:
            applied[call.args[0]] = call.args[1]
        self.assertEqual(applied, host_environment(environment))
        self.assertNotIn("EXAMPLE_USER_SECRET", [call.args[0] for call in context.setenv.call_args_list])

    def test_audio_resolves_host_binary_and_passes_clean_environment(self):
        from remote_bridge.audio import VirtualMicrophone
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            host = root / "host"
            bundle = root / "bundle"
            host.mkdir(); bundle.mkdir()
            for folder in (host, bundle):
                executable = folder / "pw-cat"
                executable.write_text("#!/bin/sh\nexit 0\n")
                executable.chmod(0o755)
            environment = self.environment()
            environment["REMOTE_MIC_HOST_PATH"] = str(host)
            environment["PATH"] = str(bundle) + os.pathsep + str(host)
            process = Mock()
            process.poll.return_value = None
            process.stdin.fileno.return_value = 17
            with patch.dict(os.environ, environment, clear=True), \
                 patch("remote_bridge.audio.subprocess.Popen", return_value=process) as popen, \
                 patch("remote_bridge.audio.os.set_blocking"), \
                 patch("remote_bridge.audio.threading.Thread"), \
                 patch("remote_bridge.audio.time.sleep"):
                VirtualMicrophone().start()
            arguments, options = popen.call_args
            self.assertEqual(arguments[0][0], str(host / "pw-cat"))
            self.assertEqual(options["env"], host_environment(environment))
            self.assertNotIn("LD_LIBRARY_PATH", options["env"])

    def test_missing_host_pipewire_does_not_fall_back_to_bundle_binary(self):
        from remote_bridge.audio import VirtualMicrophone
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            host = root / "host"; host.mkdir()
            bundle = root / "bundle"; bundle.mkdir()
            executable = bundle / "pw-cat"
            executable.write_text("#!/bin/sh\nexit 0\n"); executable.chmod(0o755)
            environment = self.environment()
            environment["REMOTE_MIC_HOST_PATH"] = str(host)
            environment["PATH"] = str(bundle) + os.pathsep + str(host)
            with patch.dict(os.environ, environment, clear=True), \
                 patch("remote_bridge.audio.subprocess.Popen") as popen:
                with self.assertRaisesRegex(FileNotFoundError, "pipewire-bin"):
                    VirtualMicrophone().start()
                popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
