#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Package an audited Ubuntu 24.04 AppDir as an amd64 Debian package.

The private runtime is shared with the AppImage. This does not download models,
modify device permissions, or install anything on the build host.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'remote-mic-linux'
APP_ID = 'io.github.panhuahao.RemoteMicLinux'
COMPATIBILITY_GLIBC = (2, 39)
PRIVATE_PATH = Path('usr/lib') / PACKAGE
NOTICE_PATH = Path('usr/share/doc') / PACKAGE
MANIFEST_PATH = NOTICE_PATH / 'build-info.json'
PRIVATE_NAMES = {'.git', '.venv', '.env', '.cache', 'local', 'models', 'recordings',
                 'config.json', 'ui.json', 'youdao-credentials.json'}
PRIVATE_SUFFIXES = {'.onnx', '.wav', '.pcm', '.raw', '.mp3', '.flac', '.log', '.pyc'}


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', value):
        raise ValueError('Invalid glibc version in build manifest')
    return tuple(int(part) for part in value.split('.'))


def source_version(path):
    module = ast.parse(path.read_text())
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == '__version__'
                for target in node.targets):
            value = ast.literal_eval(node.value)
            if isinstance(value, str) and re.fullmatch(r'\d+\.\d+\.\d+(?:[.+~][a-zA-Z0-9]+)*', value):
                return value
    raise ValueError('Missing or invalid bundled application version')


def inspect_bundle_paths(appdir):
    """Reject personal payloads, special files and links outside the AppDir."""
    for path in appdir.rglob('*'):
        relative = path.relative_to(appdir)
        if any(part in PRIVATE_NAMES for part in relative.parts) or path.suffix in PRIVATE_SUFFIXES:
            raise ValueError('Private/runtime data is not releasable: ' + str(relative))
        if path.is_symlink():
            if os.path.isabs(os.readlink(path)) or not path.resolve().is_relative_to(appdir):
                raise ValueError('Unsafe bundle symlink: ' + str(relative))
            if not path.exists():
                raise ValueError('Broken bundle symlink: ' + str(relative))
        elif not path.is_file() and not path.is_dir():
            raise ValueError('Special files are not allowed in the bundle: ' + str(relative))


def audit_elf(appdir):
    """Check the real objects, so relabelling an older manifest cannot pass."""
    maximum = (0, 0)
    count = 0
    for path in appdir.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open('rb') as stream:
            header = stream.read(20)
        if header[:4] != b'\x7fELF':
            continue
        if len(header) < 20 or header[4] != 2 or header[5] != 1 or int.from_bytes(header[18:20], 'little') != 62:
            raise ValueError('Bundle contains a non-amd64 ELF: ' + str(path.relative_to(appdir)))
        result = subprocess.run(['readelf', '--version-info', '--wide', str(path)],
                                capture_output=True, text=True, check=True)
        versions = [tuple(int(part) for part in value.split('.'))
                    for value in re.findall(r'\bGLIBC_(\d+(?:\.\d+)+)\b', result.stdout)]
        maximum = max([maximum, *versions])
        count += 1
    if not count:
        raise ValueError('AppDir does not contain an ELF runtime')
    if maximum > COMPATIBILITY_GLIBC:
        raise ValueError('AppDir requires glibc ' + '.'.join(map(str, maximum)) +
                         '; rebuild on Ubuntu 24.04 before producing this DEB')
    return {'maximum_glibc': '.'.join(map(str, maximum)), 'elf_files': count}


def validate_appdir(appdir):
    appdir = appdir.resolve(strict=True)
    inspect_bundle_paths(appdir)
    for name in ('AppRun', 'usr/bin/python3', 'app/LICENSE.md',
                 'app/README.md', 'app/README.en.md', 'app/SOURCES.md',
                 'app/assets/remote-mic-linux.svg', 'app/assets/remote-mic-linux.png',
                 'app/assets/remote-mic-linux-64.png', 'app/assets/remote-mic-linux-256.png',
                 'app/remote_bridge/__init__.py', str(MANIFEST_PATH)):
        if not (appdir / name).is_file():
            raise ValueError('Missing required AppDir file: ' + name)
    if not os.access(appdir / 'AppRun', os.X_OK):
        raise ValueError('AppRun must be executable')
    manifest = json.loads((appdir / MANIFEST_PATH).read_text())
    floor = version_tuple(manifest.get('minimum_glibc'))
    if floor > COMPATIBILITY_GLIBC:
        raise ValueError('AppDir minimum_glibc exceeds Ubuntu 24.04 (2.39)')
    version = source_version(appdir / 'app/remote_bridge/__init__.py')
    if version != manifest.get('version'):
        raise ValueError('AppDir source version does not match its build manifest')
    audit = audit_elf(appdir)
    if version_tuple(audit['maximum_glibc']) > floor:
        raise ValueError('AppDir minimum_glibc understates actual ELF requirements')
    return manifest, audit


def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stage_package(appdir, stage, manifest, audit):
    """Build only system paths; user settings and models remain outside dpkg."""
    private = stage / PRIVATE_PATH
    shutil.copytree(appdir, private, symlinks=True)
    binary = stage / 'usr/bin/remote-mic-linux'
    binary.parent.mkdir(parents=True)
    binary.write_text('#!/bin/sh\nset -eu\nunset APPIMAGE\n'
                      'exec /usr/lib/remote-mic-linux/AppRun "$@"\n')
    binary.chmod(0o755)
    desktop = stage / 'usr/share/applications' / (APP_ID + '.desktop')
    desktop.parent.mkdir(parents=True)
    desktop.write_text('\n'.join([
        '[Desktop Entry]', 'Type=Application', 'Name=Remote Mic Linux',
        'Comment=Bluetooth remote key mapping and voice dictation',
        'Comment[zh_CN]=蓝牙遥控器按键映射与语音输入',
        'Exec=remote-mic-linux --autostart', 'TryExec=remote-mic-linux',
        'Icon=remote-mic-linux', 'Terminal=false', 'Categories=AudioVideo;Audio;',
        'StartupWMClass=' + APP_ID,
        'Keywords=remote;microphone;dictation;bluetooth;',
        'Keywords[zh_CN]=remote;microphone;dictation;bluetooth;遥控器;语音;', '']))
    for size, asset in ((64, 'remote-mic-linux-64.png'),
                        (256, 'remote-mic-linux-256.png'), (512, 'remote-mic-linux.png')):
        copy_file(appdir / 'app/assets' / asset,
                  stage / f'usr/share/icons/hicolor/{size}x{size}/apps/remote-mic-linux.png')
    copy_file(appdir / 'app/assets/remote-mic-linux.svg',
              stage / 'usr/share/icons/hicolor/scalable/apps/remote-mic-linux.svg')
    documentation = stage / NOTICE_PATH
    shutil.copytree(appdir / NOTICE_PATH, documentation)
    for name in ('README.md', 'README.en.md', 'SOURCES.md', 'LICENSE.md'):
        copy_file(appdir / 'app' / name, documentation / name)
    (documentation / 'copyright').write_text(
        'Remote Mic Linux\n'
        'Copyright (C) 2026 Remote Mic Linux contributors\n'
        'Upstream source: https://github.com/panhuahao/remote-mic-linux\n\n'
        'Application code and original icons: GPL-3.0-only.\n'
        'Protocol implementation adapted from SayAll / HD838A/remote-mic-app.\n'
        'Copyright (C) 2026 SayAll contributors; GPL-3.0-only.\n'
        'Full license: /usr/share/doc/remote-mic-linux/LICENSE.md\n'
        'Source attribution: /usr/share/doc/remote-mic-linux/SOURCES.md\n\n'
        'Bundled dependencies retain their respective licenses. The collected\n'
        'system package copyright notices and build-info.json are in this\n'
        'directory. Python package licenses are retained in the private runtime\n'
        'under /usr/lib/remote-mic-linux/usr/lib/python*/site-packages.\n'
        'The GitHub icon is MIT licensed; see the private app/assets directory.\n'
        'Speech recognition model weights are not included in this package.\n')
    (documentation / 'deb-build-info.json').write_text(json.dumps({
        'package': PACKAGE, 'version': manifest['version'], 'architecture': 'amd64',
        'minimum_glibc': manifest['minimum_glibc'], 'elf_audit': audit,
        'appdir_manifest_sha256': sha256(appdir / MANIFEST_PATH),
        'user_data_managed_by_package': False,
    }, indent=2) + '\n')
    # Do not carry developer ownership, setuid bits or writable library files.
    for path in stage.rglob('*'):
        if not path.is_symlink():
            executable = bool(path.stat().st_mode & 0o111)
            path.chmod(0o755 if path.is_dir() or executable else 0o644)
    metadata = stage / 'DEBIAN'
    metadata.mkdir(mode=0o755)
    installed_size = (sum(path.stat().st_size for path in stage.rglob('*')
                          if path.is_file() and not path.is_symlink()) + 1023) // 1024
    (metadata / 'control').write_text('\n'.join([
        'Package: ' + PACKAGE, 'Version: ' + manifest['version'],
        'Section: sound', 'Priority: optional', 'Architecture: amd64',
        'Maintainer: panhuahao <8513620+panhuahao@users.noreply.github.com>',
        'Installed-Size: ' + str(installed_size),
        'Depends: libc6 (>= ' + manifest['minimum_glibc'] + '), bluez, pipewire, pipewire-bin, '
        'at-spi2-core, dbus-user-session, xwayland, ca-certificates, fontconfig-config',
        'Recommends: fonts-noto-cjk, fonts-dejavu-core',
        'Suggests: gnome-shell-extension-appindicator',
        'Homepage: https://github.com/panhuahao/remote-mic-linux',
        'Description: Bluetooth remote key mapping and voice dictation for Linux',
        ' Map Bluetooth remote buttons and dictate into the focused text field.',
        ' Includes a private Python/GTK runtime, offline recognition support and',
        ' optional Youdao recognition. Model weights are downloaded separately.',
        ' Built for Ubuntu 24.04 and newer on amd64. Desktop integration still',
        ' requires a working Bluetooth/audio session and input-device permissions.', '']))
    checksums = []
    for path in sorted(stage.rglob('*')):
        if path.is_file() and not path.is_symlink() and not path.is_relative_to(metadata):
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'md5').hexdigest()
            checksums.append(digest + '  ' + path.relative_to(stage).as_posix())
    (metadata / 'md5sums').write_text('\n'.join(checksums) + '\n')
    for path in metadata.iterdir():
        path.chmod(0o644)


def build_package(appdir, output_dir):
    appdir = appdir.resolve(strict=True)
    manifest, audit = validate_appdir(appdir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve()
    output = output_dir / f'{PACKAGE}_{manifest["version"]}_amd64.deb'
    with tempfile.TemporaryDirectory(prefix='remote-mic-deb-') as temporary:
        stage = Path(temporary) / PACKAGE
        stage.mkdir()
        stage_package(appdir, stage, manifest, audit)
        pending = Path(temporary) / output.name
        subprocess.run(['dpkg-deb', '--root-owner-group', '-Zxz', '-z6',
                        '--build', str(stage), str(pending)], check=True,
                       stdout=subprocess.DEVNULL)
        # The staging directory may be on a different filesystem from dist/.
        temporary_output = output.with_suffix('.deb.tmp')
        try:
            shutil.copyfile(pending, temporary_output)
            temporary_output.chmod(0o644)
            os.replace(temporary_output, output)
        finally:
            temporary_output.unlink(missing_ok=True)
    return {'file': str(output), 'bytes': output.stat().st_size,
            'sha256': sha256(output), 'minimum_glibc': manifest['minimum_glibc'],
            'elf_audit': audit}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--appdir', type=Path, default=ROOT / 'build/RemoteMicLinux.AppDir')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    for command in ('dpkg-deb', 'readelf'):
        if not shutil.which(command):
            parser.error('Required build tool not found: ' + command)
    try:
        print(json.dumps(build_package(args.appdir, args.output_dir), indent=2))
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        parser.exit(1, 'Cannot build Debian package: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
