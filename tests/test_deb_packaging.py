# SPDX-License-Identifier: GPL-3.0-only
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts.build_deb import (APP_ID, MANIFEST_PATH, PRIVATE_PATH, audit_elf,
                               build_package, inspect_bundle_paths, validate_appdir)


def bundle_fixture(path):
    manifest = {'app': 'Remote Mic Linux', 'version': '0.5.0',
                'minimum_glibc': '2.39', 'target': 'Ubuntu 24.04 x86_64'}
    files = {
        'AppRun': '#!/bin/sh\nexit 0\n',
        'app/remote_bridge/__init__.py': '__version__ = "0.5.0"\n',
        'app/LICENSE.md': 'GPL-3.0-only\n',
        'app/README.md': 'Readme\n', 'app/README.en.md': 'Readme\n',
        'app/SOURCES.md': 'Sources\n',
        'app/assets/remote-mic-linux.svg': '<svg/>\n',
        'app/assets/remote-mic-linux.png': 'icon',
        'app/assets/remote-mic-linux-64.png': 'icon',
        'app/assets/remote-mic-linux-256.png': 'icon',
        str(MANIFEST_PATH): json.dumps(manifest),
    }
    for name, data in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data)
    runtime = path / 'usr/bin/python3'
    runtime.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(20)
    header[:6] = b'\x7fELF\x02\x01'
    header[18:20] = (62).to_bytes(2, 'little')
    runtime.write_bytes(header)
    runtime.chmod(0o755)
    (path / 'AppRun').chmod(0o755)
    return manifest


class DebianPackagingTests(unittest.TestCase):
    def test_models_personal_settings_and_recordings_are_rejected(self):
        for name in ('app/config.json', 'app/youdao-credentials.json',
                     'app/models/model.onnx', 'app/local/sample.wav'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = root / name
                target.parent.mkdir(parents=True)
                target.write_text('private payload')
                with self.assertRaisesRegex(ValueError, 'Private/runtime data'):
                    inspect_bundle_paths(root)

    def test_symlink_cannot_import_files_outside_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'AppDir'
            root.mkdir()
            (Path(directory) / 'outside').write_text('private')
            (root / 'escape').symlink_to('../outside')
            with self.assertRaisesRegex(ValueError, 'Unsafe bundle symlink'):
                inspect_bundle_paths(root)

    def test_elf_abi_cannot_be_hidden_by_manifest_relabelling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle_fixture(root)
            result = subprocess.CompletedProcess([], 0, 'Name: GLIBC_2.40\n', '')
            with patch('scripts.build_deb.subprocess.run', return_value=result):
                with self.assertRaisesRegex(ValueError, 'requires glibc 2.40'):
                    validate_appdir(root)

    def test_non_amd64_runtime_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle_fixture(root)
            runtime = root / 'usr/bin/python3'
            header = bytearray(runtime.read_bytes())
            header[18:20] = (183).to_bytes(2, 'little')
            runtime.write_bytes(header)
            with self.assertRaisesRegex(ValueError, 'non-amd64 ELF'):
                audit_elf(root)

    def test_manifest_version_and_abi_floor_must_match_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = bundle_fixture(root)
            manifest['version'] = '0.4.0'
            (root / MANIFEST_PATH).write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'version does not match'):
                validate_appdir(root)
            manifest.update(version='0.5.0', minimum_glibc='2.38')
            (root / MANIFEST_PATH).write_text(json.dumps(manifest))
            with patch('scripts.build_deb.audit_elf', return_value={
                    'maximum_glibc': '2.39', 'elf_files': 1}):
                with self.assertRaisesRegex(ValueError, 'understates actual'):
                    validate_appdir(root)

    @unittest.skipUnless(shutil.which('dpkg-deb'), 'dpkg-deb is not installed')
    def test_real_deb_archive_installs_only_root_owned_system_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / 'AppDir'
            bundle.mkdir()
            bundle_fixture(bundle)
            # Exercise the real archive builder; ELF behaviour is tested above.
            with patch('scripts.build_deb.audit_elf', return_value={
                    'maximum_glibc': '2.39', 'elf_files': 1}):
                result = build_package(bundle, root / 'dist')
            package = result['file']
            self.assertEqual(Path(package).name, 'remote-mic-linux_0.5.0_amd64.deb')
            control = subprocess.check_output(['dpkg-deb', '--field', package], text=True)
            self.assertIn('Architecture: amd64', control)
            self.assertIn('libc6 (>= 2.39)', control)
            self.assertIn('at-spi2-core', control)
            self.assertIn('pipewire-bin', control)
            data = subprocess.check_output(['dpkg-deb', '--fsys-tarfile', package])
            with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                members = archive.getmembers()
                for member in members:
                    self.assertEqual((member.uid, member.gid), (0, 0))
                    self.assertEqual(member.mode & 0o7022, 0)
                    self.assertTrue(member.name in ('.', './usr') or member.name.startswith('./usr/'))
                names = {member.name for member in members}
                self.assertIn('./usr/share/applications/' + APP_ID + '.desktop', names)
                self.assertIn('./' + str(PRIVATE_PATH) + '/AppRun', names)
                launcher = archive.extractfile('./usr/bin/remote-mic-linux').read().decode()
                self.assertIn('exec /usr/lib/remote-mic-linux/AppRun "$@"', launcher)
            metadata = subprocess.check_output(['dpkg-deb', '--ctrl-tarfile', package])
            with tarfile.open(fileobj=io.BytesIO(metadata)) as archive:
                self.assertEqual({member.name for member in archive.getmembers()},
                                 {'.', './control', './md5sums'})


if __name__ == '__main__':
    unittest.main()
