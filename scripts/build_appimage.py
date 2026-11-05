#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build the Ubuntu 24.04 x86_64 Python/GTK runtime and AppImage."""
import argparse
import ctypes.util
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import sysconfig

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SHA256 = '617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46'
MINIMUM_GLIBC = '2.39'
GLIBC_BASELINE = (2, 39)
MODULES = ['gi', 'cairo', 'numpy', 'sherpa_onnx', 'bleak', 'dbus_fast',
           'evdev', 'websockets']
DISTRIBUTIONS = ['PyGObject', 'pycairo', 'numpy', 'sherpa-onnx', 'sherpa-onnx-core',
                 'bleak', 'dbus-fast', 'evdev', 'websockets']
IGNORE = shutil.ignore_patterns('__pycache__', '*.pyc', 'tests', 'test', '*.a')
# The host owns glibc and the graphics driver stack. Mixing either with a
# private copy can break its loader, NSS modules or hardware drivers.
HOST_LIBRARIES = re.compile(
    r'^(?:lib(?:c|m|mvec|pthread|dl|rt|resolv|util|anl)\.so|libnss_|ld-linux|'
    r'lib(?:GL|GLX|GLdispatch|OpenGL|EGL|GLESv1_CM|GLESv2|vulkan|drm|gbm)(?:[._-]))')


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True, ignore=IGNORE)
    else:
        shutil.copy2(source, destination)


def c_environment():
    return {**os.environ, 'LC_ALL': 'C'}


def verify_build_host():
    if platform.machine() != 'x86_64':
        raise RuntimeError('This build recipe targets x86_64')
    libc, version = platform.libc_ver()
    if libc != 'glibc' or not re.fullmatch(r'\d+(?:\.\d+)+', version):
        raise RuntimeError('A glibc build environment is required')
    if tuple(map(int, version.split('.'))) > GLIBC_BASELINE:
        raise RuntimeError('Build host glibc ' + version +
                           ' is newer than 2.39; build in Ubuntu 24.04')
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('Build with Ubuntu 24.04 Python 3.12')


def native_dependencies(path):
    result = subprocess.run(['ldd', str(path)], capture_output=True, text=True,
                            env=c_environment())
    for line in result.stdout.splitlines():
        if '=> not found' in line:
            raise RuntimeError('Unresolved native dependency for ' + str(path) + ': ' + line.strip())
        match = re.search(r'=>\s+(/.+?)\s+\(0x[0-9a-fA-F]+\)', line)
        if match:
            yield Path(match.group(1))
    if result.returncode and not any(value in result.stdout + result.stderr
                                    for value in ('not a dynamic executable', 'statically linked')):
        raise RuntimeError('Could not inspect native dependencies: ' + str(path))


def elf_files(directory):
    for path in sorted(directory.rglob('*')):
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as stream:
                header = stream.read(20)
            if header[:4] == b'\x7fELF':
                if (len(header) < 20 or header[4:6] != b'\x02\x01' or
                        int.from_bytes(header[18:20], 'little') != 62):
                    raise RuntimeError('Non-x86_64 ELF in bundle: ' + str(path))
                yield path


def needed_glibc_versions(output):
    """Read imported symbol versions, excluding a library's own definitions."""
    needs = False
    for line in output.splitlines():
        if line.lstrip().startswith('Version '):
            needs = line.lstrip().startswith('Version needs section ')
        if needs:
            for version in re.findall(r'\bName: GLIBC_(\d+(?:\.\d+)+)\b', line):
                yield tuple(map(int, version.split('.')))


def audit_elf(directory):
    maximum = (0, 0)
    count = 0
    for path in elf_files(directory):
        result = subprocess.run(['readelf', '--version-info', '--wide', str(path)],
                                capture_output=True, text=True, check=True,
                                env=c_environment())
        required = max(needed_glibc_versions(result.stdout), default=(0, 0))
        if required > GLIBC_BASELINE:
            raise RuntimeError(str(path.relative_to(directory)) + ' requires glibc ' +
                               '.'.join(map(str, required)) + '; maximum allowed is 2.39')
        maximum = max(maximum, required)
        count += 1
    if not count:
        raise RuntimeError('Bundle contains no ELF runtime')
    return {'maximum_glibc': '.'.join(map(str, maximum)), 'elf_files': count}


def system_library(name):
    soname = ctypes.util.find_library(name)
    multiarch = sysconfig.get_config_var('MULTIARCH') or 'x86_64-linux-gnu'
    for directory in (Path('/usr/lib') / multiarch, Path('/lib') / multiarch,
                      Path('/usr/lib'), Path('/lib')):
        candidate = directory / str(soname)
        if soname and candidate.is_file():
            return candidate
    raise RuntimeError('Missing native library: ' + name)


def system_tool(name, patterns=()):
    found = shutil.which(name)
    if found:
        return Path(found)
    for pattern in patterns:
        for candidate in sorted(Path('/usr/lib').glob(pattern)):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
    raise RuntimeError('Missing system tool: ' + name)


def copy_desktop_runtime(app, sources):
    """Include libraries loaded with dlopen(), which ldd cannot discover."""
    searches = (
        ('*/gtk-3.0/*/immodules/*.so', 'usr/lib/gtk-3.0/immodules'),
        ('*/gdk-pixbuf-2.0/*/loaders/*.so', 'usr/lib/gdk-pixbuf-2.0/loaders'),
    )
    for pattern, destination in searches:
        modules = sorted(Path('/usr/lib').glob(pattern))
        if not modules:
            raise RuntimeError('Missing GTK runtime modules: ' + pattern)
        for source in modules:
            copy(source, app / destination / source.name)
            sources.add(source)
    for name, patterns in (
            ('gtk-query-immodules-3.0', ('*/libgtk-3-0*/gtk-query-immodules-3.0',)),
            ('gdk-pixbuf-query-loaders', ('*/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders',))):
        source = system_tool(name, patterns)
        copy(source, app / 'usr/bin' / name)
        sources.add(source)
    for name in ('libdconfsettings.so', 'libgiognutls.so'):
        matches = sorted(Path('/usr/lib').glob('*/gio/modules/' + name))
        if not matches:
            raise RuntimeError('Missing GIO runtime module: ' + name)
        copy(matches[0], app / 'usr/lib/gio/modules' / name)
        sources.add(matches[0])
    query = system_tool('gio-querymodules', ('*/glib-2.0/gio-querymodules',))
    subprocess.run([str(query), str(app / 'usr/lib/gio/modules')], check=True)
    for name in ('Adwaita', 'hicolor'):
        source = Path('/usr/share/icons') / name
        if not (source / 'index.theme').is_file():
            raise RuntimeError('Missing icon theme: ' + name)
        copy(source, app / 'usr/share/icons' / name)
        sources.add(source)
    source = Path('/usr/share/glib-2.0/schemas')
    destination = app / 'usr/share/glib-2.0/schemas'
    destination.mkdir(parents=True)
    for schema in sorted(source.iterdir()):
        if schema.name.endswith(('.xml', '.override')):
            copy(schema, destination / schema.name)
            sources.add(schema)
    subprocess.run(['glib-compile-schemas', '--strict', str(destination)], check=True)


def runner_script(pyver):
    return '''#!/bin/sh
set -eu
APPDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export REMOTE_MIC_HOST_PATH="$PATH"
export REMOTE_MIC_HOST_XDG_DATA_DIRS="${XDG_DATA_DIRS-}"
export REMOTE_MIC_HOST_GDK_BACKEND="${GDK_BACKEND-}"
if [ "${GTK_MODULES+x}" = x ]; then
    export REMOTE_MIC_HOST_GTK_MODULES="$GTK_MODULES"
else
    unset REMOTE_MIC_HOST_GTK_MODULES
fi
if [ "${GTK_PATH+x}" = x ]; then
    export REMOTE_MIC_HOST_GTK_PATH="$GTK_PATH"
else
    unset REMOTE_MIC_HOST_GTK_PATH
fi
if [ "${GIO_EXTRA_MODULES+x}" = x ]; then
    export REMOTE_MIC_HOST_GIO_EXTRA_MODULES="$GIO_EXTRA_MODULES"
else
    unset REMOTE_MIC_HOST_GIO_EXTRA_MODULES
fi
unset GTK_MODULES GTK_PATH GIO_EXTRA_MODULES
export REMOTE_MIC_BUNDLE=1
export APPDIR
export PYTHONHOME="$APPDIR/usr"
export PYTHONPATH="$APPDIR/usr/lib/@PYVER@/site-packages"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export LD_LIBRARY_PATH="$APPDIR/usr/lib/remote-mic-linux"
export GI_TYPELIB_PATH="$APPDIR/usr/lib/girepository-1.0"
export GIO_MODULE_DIR="$APPDIR/usr/lib/gio/modules"
export XDG_DATA_DIRS="$APPDIR/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
export PATH="$APPDIR/usr/bin:$PATH"
export GDK_BACKEND=x11
umask 077
runtime_cache=$(LD_LIBRARY_PATH= mktemp -d "${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/remote-mic-linux.XXXXXXXX")
cleanup() { LD_LIBRARY_PATH= rm -rf -- "$runtime_cache"; }
trap cleanup EXIT
export GDK_PIXBUF_MODULE_FILE="$runtime_cache/pixbuf-loaders.cache"
export GTK_IM_MODULE_FILE="$runtime_cache/gtk-immodules.cache"
# GLib's query tools may otherwise replace non-ASCII install paths with '?'.
CHARSET=UTF-8 "$APPDIR/usr/bin/gdk-pixbuf-query-loaders" "$APPDIR/usr/lib/gdk-pixbuf-2.0/loaders/"*.so > "$GDK_PIXBUF_MODULE_FILE"
CHARSET=UTF-8 "$APPDIR/usr/bin/gtk-query-immodules-3.0" "$APPDIR/usr/lib/gtk-3.0/immodules/"*.so > "$GTK_IM_MODULE_FILE"
cd "$APPDIR/app"
if [ "$#" -eq 0 ]; then set -- --autostart; fi
"$APPDIR/usr/bin/python3" -s -m remote_bridge "$@" <&0 &
app_pid=$!
trap 'kill -HUP "$app_pid" 2>/dev/null || :; wait "$app_pid" 2>/dev/null || :; exit 129' HUP
trap 'kill -INT "$app_pid" 2>/dev/null || :; wait "$app_pid" 2>/dev/null || :; exit 130' INT
trap 'kill -TERM "$app_pid" 2>/dev/null || :; wait "$app_pid" 2>/dev/null || :; exit 143' TERM
status=0
wait "$app_pid" || status=$?
exit "$status"
'''.replace('@PYVER@', pyver)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True,
                        help='Official AppImage type2 runtime; SHA256 is checked')
    parser.add_argument('--runtime-license', type=Path, required=True)
    args = parser.parse_args()
    verify_build_host()
    if hashlib.sha256(args.runtime.read_bytes()).hexdigest() != RUNTIME_SHA256:
        raise RuntimeError('AppImage runtime checksum mismatch')
    if args.runtime_license.stat().st_size < 100:
        raise RuntimeError('Missing runtime license')
    sys.path.insert(0, str(ROOT))
    from remote_bridge import __version__
    from remote_bridge.identity import APP_ID
    app = ROOT / 'build/RemoteMicLinux.AppDir'
    if app.exists():
        shutil.rmtree(app)
    app.mkdir(parents=True)
    pyver = f'python{sys.version_info.major}.{sys.version_info.minor}'
    stdlib = app / 'usr/lib' / pyver
    site = stdlib / 'site-packages'
    executable = Path(sys.executable).resolve()
    sources = {executable}
    copy(executable, app / 'usr/bin/python3')
    shutil.copytree(sysconfig.get_path('stdlib'), stdlib,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.a', 'test',
                        'tests', 'idlelib', 'tkinter', 'turtledemo', 'ensurepip', 'config-*',
                        'dist-packages', 'site-packages'))
    for name in MODULES:
        module = importlib.import_module(name)
        source = Path(module.__file__)
        source = source.parent if hasattr(module, '__path__') else source
        copy(source, site / source.name)
        for suffix in ('.libs', '.data'):
            extra = source.with_name(name + suffix)
            if extra.is_dir():
                copy(extra, site / extra.name)
    for name in DISTRIBUTIONS:
        metadata = Path(importlib.metadata.distribution(name)._path)
        copy(metadata, site / metadata.name)
    # PipeWire client/server plugins must match the host. VirtualMicrophone uses
    # the host pw-cat with a clean environment instead of a private copy.
    for name in ('wl-copy', 'wl-paste'):
        source = system_tool(name)
        copy(source, app / 'usr/bin' / name)
        sources.add(source)
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Atspi', '2.0')
    gi.require_version('AyatanaAppIndicator3', '0.1')
    gi.require_version('GdkX11', '3.0')
    from gi.repository import Gtk, Atspi, AyatanaAppIndicator3, GdkX11
    repository = gi.Repository.get_default()
    for namespace in repository.get_loaded_namespaces():
        source = Path(repository.get_typelib_path(namespace))
        copy(source, app / 'usr/lib/girepository-1.0' / source.name)
        sources.add(source)
    copy_desktop_runtime(app, sources)
    libraries = app / 'usr/lib/remote-mic-linux'
    libraries.mkdir(parents=True)
    roots = list(elf_files(app))
    for name in ('gtk-3', 'gdk-3', 'atspi', 'gdk_pixbuf-2.0', 'X11', 'ayatana-appindicator3'):
        seed = system_library(name)
        roots.append(seed)
        copy(seed, libraries / seed.name)
        sources.add(seed)
    for seed in roots:
        for dependency in native_dependencies(seed):
            if HOST_LIBRARIES.match(dependency.name) or dependency.is_relative_to(app):
                continue
            copy(dependency, libraries / dependency.name)
            sources.add(dependency)
    payload = app / 'app'
    payload.mkdir()
    for name in ('remote_bridge', 'assets', 'config.example.json', 'install_model.py',
                 'install_desktop.py', 'README.md', 'README.en.md', 'LICENSE.md',
                 'SOURCES.md', 'RELEASE.md', 'CHANGELOG.md', 'docs'):
        copy(ROOT / name, payload / name)
    copy(ROOT / 'assets/remote-mic-linux.png', app / 'remote-mic-linux.png')
    copy(ROOT / 'assets/remote-mic-linux.png', app / '.DirIcon')
    (app / (APP_ID + '.desktop')).write_text('\n'.join([
        '[Desktop Entry]', 'Type=Application', 'Name=Remote Mic Linux',
        'Comment=Bluetooth remote key mapping and voice dictation', 'Exec=AppRun',
        'Icon=remote-mic-linux', 'Terminal=false', 'Categories=AudioVideo;Audio;',
        'StartupWMClass=' + APP_ID, '']))
    (app / 'AppRun').write_text(runner_script(pyver))
    (app / 'AppRun').chmod(0o755)
    notice = app / 'usr/share/doc/remote-mic-linux'
    notice.mkdir(parents=True)
    copy(args.runtime_license, notice / 'AppImage-runtime-LICENSE')
    packages = {pyver, 'lib' + pyver + '-stdlib', 'lib' + pyver + '-minimal',
                'python3-gi', 'python3-cairo', 'wl-clipboard', 'libgtk-3-bin',
                'gir1.2-ayatanaappindicator3-0.1', 'libgdk-pixbuf2.0-bin',
                'librsvg2-common', 'glib-networking', 'glib-networking-common',
                'dconf-gsettings-backend', 'adwaita-icon-theme', 'hicolor-icon-theme',
                'gsettings-desktop-schemas'}
    # Merged-/usr systems may report /lib from ldd while dpkg records /usr/lib.
    # Query both names so every bundled native dependency retains its notice.
    package_paths = sources | {path.resolve() for path in sources}
    result = subprocess.run(['dpkg-query', '-S', *map(str, sorted(package_paths))],
                            capture_output=True, text=True, env=c_environment())
    for line in result.stdout.splitlines():
        if ': ' in line:
            for owner in line.split(': ', 1)[0].split(', '):
                # dpkg-query may also print diversion descriptions, which
                # are not package names and have no copyright directory.
                if re.fullmatch(r'[a-z0-9][a-z0-9+.-]+(?::[a-z0-9-]+)?', owner):
                    packages.add(owner.split(':')[0])
    for name in sorted(packages):
        license_file = Path('/usr/share/doc') / name / 'copyright'
        if license_file.is_file():
            copy(license_file, notice / (name + '-copyright'))
    audit = audit_elf(app)
    versions = {name: importlib.metadata.version(name) for name in DISTRIBUTIONS}
    (notice / 'build-info.json').write_text(json.dumps({
        'app': 'Remote Mic Linux', 'version': __version__, 'target': 'Ubuntu 24.04 x86_64',
        'minimum_glibc': MINIMUM_GLIBC, 'python': platform.python_version(),
        'elf_audit': audit, 'runtime_sha256': RUNTIME_SHA256, 'dependencies': versions,
        'system_packages': sorted(packages), 'host_tools': ['pw-cat'],
    }, indent=2) + '\n')
    output = ROOT / 'dist' / f'Remote-Mic-Linux-{__version__}-x86_64.AppImage'
    output.parent.mkdir(exist_ok=True)
    squash = ROOT / 'build/payload.squashfs'
    if squash.exists():
        squash.unlink()
    subprocess.run(['mksquashfs', str(app), str(squash), '-noappend', '-comp', 'gzip',
                    '-processors', '2', '-no-progress', '-all-root'], check=True,
                   stdout=subprocess.DEVNULL)
    temporary = output.with_suffix('.AppImage.tmp')
    with temporary.open('wb') as stream:
        stream.write(args.runtime.read_bytes())
        with squash.open('rb') as data:
            shutil.copyfileobj(data, stream)
    temporary.chmod(0o755)
    os.replace(temporary, output)
    print(json.dumps({'file': str(output), 'bytes': output.stat().st_size,
        'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'bundled_libraries': len(list(libraries.iterdir())), 'elf_audit': audit}, indent=2))


if __name__ == '__main__':
    main()
