# SPDX-License-Identifier: GPL-3.0-only
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.build_appimage import (HOST_LIBRARIES, audit_elf, native_dependencies,
                                    needed_glibc_versions, runner_script, verify_build_host)


def elf_fixture(path, machine=62):
    header = bytearray(20)
    header[:6] = b'\x7fELF\x02\x01'
    header[18:20] = machine.to_bytes(2, 'little')
    path.write_bytes(header)


class AppImagePackagingTests(unittest.TestCase):
    def test_newer_build_host_is_rejected_before_packaging(self):
        with patch('scripts.build_appimage.platform.machine', return_value='x86_64'), \
             patch('scripts.build_appimage.platform.libc_ver', return_value=('glibc', '2.42')):
            with self.assertRaisesRegex(RuntimeError, 'newer than 2.39'):
                verify_build_host()

    def test_ubuntu24_build_environment_is_accepted(self):
        with patch('scripts.build_appimage.platform.machine', return_value='x86_64'), \
             patch('scripts.build_appimage.platform.libc_ver', return_value=('glibc', '2.39')), \
             patch('scripts.build_appimage.sys.version_info', (3, 12, 3)):
            verify_build_host()

    def test_symbol_audit_uses_requirements_not_exported_definitions(self):
        output = """Version definition section '.gnu.version_d' contains 1 entry:
  0x001c: Rev: 1 Flags: none Index: 2 Cnt: 1 Name: GLIBC_2.99
Version needs section '.gnu.version_r' contains 1 entry:
  0x0010: Name: GLIBC_2.2.5 Flags: none Version: 2
  0x0020: Name: GLIBC_2.39 Flags: none Version: 3
"""
        self.assertEqual(list(needed_glibc_versions(output)), [(2, 2, 5), (2, 39)])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            elf_fixture(root / 'runtime')
            (root / 'README').write_text('not ELF')
            result = subprocess.CompletedProcess([], 0, output, '')
            with patch('scripts.build_appimage.subprocess.run', return_value=result):
                self.assertEqual(audit_elf(root), {'maximum_glibc': '2.39', 'elf_files': 1})

    def test_newer_glibc_required_by_any_object_blocks_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            elf_fixture(root / 'newer-library.so')
            result = subprocess.CompletedProcess([], 0,
                "Version needs section '.gnu.version_r' contains 1 entry:\n"
                '  Name: GLIBC_2.40 Flags: none Version: 2\n', '')
            with patch('scripts.build_appimage.subprocess.run', return_value=result):
                with self.assertRaisesRegex(RuntimeError, 'newer-library.so requires glibc 2.40'):
                    audit_elf(root)

    def test_wrong_architecture_and_unresolved_dependencies_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            elf_fixture(root / 'arm.so', machine=183)
            with self.assertRaisesRegex(RuntimeError, 'Non-x86_64'):
                audit_elf(root)
        result = subprocess.CompletedProcess([], 0, 'libmissing.so => not found\n', '')
        with patch('scripts.build_appimage.subprocess.run', return_value=result):
            with self.assertRaisesRegex(RuntimeError, 'Unresolved native dependency'):
                list(native_dependencies(Path('/app/runtime')))

    def test_glibc_and_graphics_stacks_remain_owned_by_host(self):
        for name in ('libc.so.6', 'libm.so.6', 'libmvec.so.1', 'libnss_dns.so.2',
                     'ld-linux-x86-64.so.2', 'libGL.so.1', 'libGLX_mesa.so.0',
                     'libEGL.so.1', 'libdrm_amdgpu.so.1'):
            with self.subTest(name=name):
                self.assertIsNotNone(HOST_LIBRARIES.match(name))
        for name in ('libglib-2.0.so.0', 'libstdc++.so.6', 'libgobject-2.0.so.0'):
            with self.subTest(name=name):
                self.assertIsNone(HOST_LIBRARIES.match(name))

    def test_real_runner_relocates_private_caches_and_preserves_exit_status(self):
        with tempfile.TemporaryDirectory(prefix='appimage path with spaces ') as directory:
            root = Path(directory)
            app = root / 'AppDir'; (app / 'app').mkdir(parents=True)
            binary = app / 'usr/bin'; binary.mkdir(parents=True)
            runtime = root / 'session'; runtime.mkdir()
            for name in ('gdk-pixbuf-2.0/loaders', 'gtk-3.0/immodules'):
                modules = app / 'usr/lib' / name
                modules.mkdir(parents=True)
                (modules / 'test.so').write_text('module fixture')
            for name in ('gdk-pixbuf-query-loaders', 'gtk-query-immodules-3.0'):
                path = binary / name
                path.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
                path.chmod(0o755)
            python = binary / 'python3'
            python.write_text('#!/bin/sh\nset -eu\n'
                'test -s "$GTK_IM_MODULE_FILE"\ntest -s "$GDK_PIXBUF_MODULE_FILE"\n'
                'test "${GTK_MODULES+x}" != x\ntest "${GTK_PATH+x}" != x\n'
                'test "${GIO_EXTRA_MODULES+x}" != x\n'
                'test "${REMOTE_MIC_HOST_GTK_MODULES-}" = "appmenu-gtk-module"\n'
                'test "${REMOTE_MIC_HOST_GTK_PATH+x}" = x\n'
                'test "$REMOTE_MIC_HOST_GTK_PATH" = ""\n'
                'test "${REMOTE_MIC_HOST_GIO_EXTRA_MODULES+x}" != x\n'
                'printf "args=%s\\n" "$*"\n'
                'printf "host_data=%s\\n" "$REMOTE_MIC_HOST_XDG_DATA_DIRS"\n'
                'printf "host_backend=%s\\n" "$REMOTE_MIC_HOST_GDK_BACKEND"\n'
                'cat "$GTK_IM_MODULE_FILE" "$GDK_PIXBUF_MODULE_FILE"\n'
                'exit "$TEST_EXIT_STATUS"\n')
            python.chmod(0o755)
            runner = app / 'AppRun'
            runner.write_text(runner_script('python3.12')); runner.chmod(0o755)
            for status in (0, 7):
                environment = {'PATH': os.defpath, 'HOME': str(root),
                               'XDG_RUNTIME_DIR': str(runtime), 'XDG_DATA_DIRS': '/host/share',
                               'GDK_BACKEND': 'wayland', 'TEST_EXIT_STATUS': str(status),
                               'GTK_MODULES': 'appmenu-gtk-module', 'GTK_PATH': '',
                               # A stale backup must not turn an originally
                               # unset host variable into a configured one.
                               'REMOTE_MIC_HOST_GIO_EXTRA_MODULES': '/stale/backup'}
                result = subprocess.run([str(runner), '--version'], env=environment,
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertIn('args=-s -m remote_bridge --version', result.stdout)
                self.assertIn('host_data=/host/share', result.stdout)
                self.assertIn('host_backend=wayland', result.stdout)
                self.assertIn(str(app / 'usr/lib/gtk-3.0/immodules/test.so'), result.stdout)
                self.assertIn(str(app / 'usr/lib/gdk-pixbuf-2.0/loaders/test.so'), result.stdout)
                self.assertEqual(list(runtime.iterdir()), [])
            # A loader failure must stop launch and still remove its private cache.
            (binary / 'gdk-pixbuf-query-loaders').write_text('#!/bin/sh\nexit 23\n')
            result = subprocess.run([str(runner)], env=environment, capture_output=True,
                                    text=True, timeout=5)
            self.assertEqual(result.returncode, 23)
            self.assertNotIn('args=', result.stdout)
            self.assertEqual(list(runtime.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
