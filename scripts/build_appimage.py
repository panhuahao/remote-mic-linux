#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build a self-contained Python/GTK AppImage for this Ubuntu ABI."""
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

ROOT=Path(__file__).resolve().parents[1]
RUNTIME_SHA256='617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46'
MODULES=['gi','cairo','numpy','sherpa_onnx','bleak','dbus_fast','evdev','websockets','typing_extensions']
DISTRIBUTIONS=['PyGObject','pycairo','numpy','sherpa-onnx','sherpa-onnx-core','bleak','dbus-fast','evdev','websockets','typing_extensions']
IGNORE=shutil.ignore_patterns('__pycache__','*.pyc','tests','test','*.a')

def copy(source,destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    if source.is_dir():shutil.copytree(source,destination,dirs_exist_ok=True,ignore=IGNORE)
    else:shutil.copy2(source,destination)

def native_dependencies(path):
    result=subprocess.run(['ldd',str(path)],capture_output=True,text=True)
    for line in result.stdout.splitlines():
        if '=> not found' in line:
            raise RuntimeError('Unresolved native dependency for '+str(path)+': '+line.strip())
        match=re.search(r'=>\s+(/.+?)\s+\(0x[0-9a-fA-F]+\)',line)
        if match:yield Path(match.group(1))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True,help='Official AppImage type2 runtime; SHA256 is checked')
    parser.add_argument('--runtime-license',type=Path,required=True)
    args=parser.parse_args()
    if platform.machine()!='x86_64':raise SystemExit('This build recipe currently targets x86_64')
    if hashlib.sha256(args.runtime.read_bytes()).hexdigest()!=RUNTIME_SHA256:
        raise SystemExit('AppImage runtime checksum mismatch')
    if args.runtime_license.stat().st_size<100:raise SystemExit('Missing runtime license')
    sys.path.insert(0,str(ROOT))
    from remote_bridge import __version__
    app=ROOT/'build/RemoteMicLinux.AppDir'
    if app.exists():shutil.rmtree(app)
    app.mkdir(parents=True)
    pyver=f'python{sys.version_info.major}.{sys.version_info.minor}'
    stdlib=app/'usr/lib'/pyver;site=stdlib/'site-packages'
    copy(Path(sys.executable).resolve(),app/'usr/bin/python3')
    shutil.copytree(sysconfig.get_path('stdlib'),stdlib,
                    ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.a','test','tests','idlelib','tkinter','turtledemo','ensurepip','config-*','dist-packages','site-packages'))
    for name in MODULES:
        module=importlib.import_module(name);source=Path(module.__file__)
        source=source.parent if hasattr(module,'__path__') else source
        copy(source,site/source.name)
        for suffix in ('.libs','.data'):
            extra=source.with_name(name+suffix)
            if extra.is_dir():copy(extra,site/extra.name)
    for name in DISTRIBUTIONS:
        dist=importlib.metadata.distribution(name);metadata=Path(dist._path)
        copy(metadata,site/metadata.name)
    for tool in ('pw-cat','wl-copy','wl-paste'):
        source=shutil.which(tool)
        if not source:raise SystemExit('Missing system tool: '+tool)
        copy(Path(source),app/'usr/bin'/tool)
    import gi
    gi.require_version('Gtk','3.0');gi.require_version('Atspi','2.0');gi.require_version('AyatanaAppIndicator3','0.1');gi.require_version('GdkX11','3.0')
    from gi.repository import Gtk, Atspi, AyatanaAppIndicator3, GdkX11
    repository=gi.Repository.get_default()
    for namespace in repository.get_loaded_namespaces():
        path=Path(repository.get_typelib_path(namespace))
        copy(path,app/'usr/lib/girepository-1.0'/path.name)
    libraries=app/'usr/lib/remote-mic-linux';libraries.mkdir(parents=True)
    roots=list((app/'usr/bin').iterdir())+list(stdlib.rglob('*.so'))+list(stdlib.rglob('*.so.*'))
    for name in ('gtk-3','gdk-3','atspi','gdk_pixbuf-2.0','X11','ayatana-appindicator3'):
        soname=ctypes.util.find_library(name)
        path=Path('/usr/lib/x86_64-linux-gnu')/str(soname)
        if not path.is_file():raise SystemExit('Missing native library: '+name)
        roots.append(path)
    # Keep the host glibc and graphics drivers. The bundle targets Ubuntu 26.04
    # x86_64; it is not advertised as an all-distribution Linux binary.
    excluded=re.compile(r'^(libc\.so|libm\.so|libpthread\.so|libdl\.so|librt\.so|libresolv\.so|libutil\.so|ld-linux|libnss_)')
    sources=set()
    for seed in roots:
        deps=list(native_dependencies(seed))
        if seed.parent==Path('/usr/lib/x86_64-linux-gnu'):deps.append(seed)
        for dependency in deps:
            if excluded.match(dependency.name) or dependency.is_relative_to(app):continue
            copy(dependency,libraries/dependency.name);sources.add(dependency)
    payload=app/'app';payload.mkdir()
    for name in ('remote_bridge','assets','config.example.json','install_model.py','install_desktop.py','README.md','LICENSE.md','SOURCES.md','RELEASE.md','CHANGELOG.md','docs'):
        copy(ROOT/name,payload/name)
    copy(ROOT/'assets/remote-mic-linux.png',app/'remote-mic-linux.png')
    copy(ROOT/'assets/remote-mic-linux.png',app/'.DirIcon')
    from remote_bridge.identity import APP_ID
    desktop='\n'.join(['[Desktop Entry]','Type=Application','Name=Remote Mic Linux',
        'Comment=Bluetooth remote key mapping and voice dictation','Exec=AppRun',
        'Icon=remote-mic-linux','Terminal=false','Categories=AudioVideo;Audio;',
        'StartupWMClass='+APP_ID,''])
    (app/(APP_ID+'.desktop')).write_text(desktop)
    runner='\n'.join(['#!/bin/sh','set -eu',
        'APPDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)',
        'export REMOTE_MIC_HOST_PATH="$PATH"','export REMOTE_MIC_BUNDLE=1',
        'export APPDIR','export PYTHONHOME="$APPDIR/usr"',
        'export PYTHONPATH="$APPDIR/usr/lib/'+pyver+'/site-packages"',
        'export PYTHONNOUSERSITE=1','export PYTHONDONTWRITEBYTECODE=1',
        'export LD_LIBRARY_PATH="$APPDIR/usr/lib/remote-mic-linux"',
        'export GI_TYPELIB_PATH="$APPDIR/usr/lib/girepository-1.0"',
        'export PATH="$APPDIR/usr/bin:$PATH"','export GDK_BACKEND=x11',
        'cd "$APPDIR/app"','if [ "$#" -eq 0 ]; then set -- --autostart; fi',
        'exec "$APPDIR/usr/bin/python3" -s -m remote_bridge "$@"',''])
    (app/'AppRun').write_text(runner);(app/'AppRun').chmod(0o755)
    notice=app/'usr/share/doc/remote-mic-linux';notice.mkdir(parents=True)
    copy(args.runtime_license,notice/'AppImage-runtime-LICENSE')
    packages={'python3.14','libpython3.14-stdlib','python3-gi','python3-cairo','python3-numpy','pipewire-bin','wl-clipboard','gir1.2-ayatanaappindicator3-0.1'}
    result=subprocess.run(['dpkg-query','-S',*[str(p) for p in sorted(sources)]],capture_output=True,text=True)
    for line in result.stdout.splitlines():
        if ': ' in line:packages.add(line.split(': ',1)[0].split(':')[0])
    for name in sorted(packages):
        license=Path('/usr/share/doc')/name/'copyright'
        if license.is_file():copy(license,notice/(name+'-copyright'))
    versions={name:importlib.metadata.version(name) for name in DISTRIBUTIONS}
    (notice/'build-info.json').write_text(json.dumps({'app':'Remote Mic Linux','version':__version__,
        'target':'Ubuntu 26.04 x86_64','python':platform.python_version(),
        'runtime_sha256':RUNTIME_SHA256,'dependencies':versions,'system_packages':sorted(packages)},indent=2))
    output=ROOT/'dist'/f'Remote-Mic-Linux-{__version__}-x86_64.AppImage';output.parent.mkdir(exist_ok=True)
    squash=ROOT/'build/payload.squashfs'
    if squash.exists():squash.unlink()
    subprocess.run(['mksquashfs',str(app),str(squash),'-noappend','-comp','gzip','-processors','2','-no-progress','-all-root'],check=True,stdout=subprocess.DEVNULL)
    temporary=output.with_suffix('.AppImage.tmp')
    with temporary.open('wb') as stream:
        stream.write(args.runtime.read_bytes())
        with squash.open('rb') as data:shutil.copyfileobj(data,stream)
    temporary.chmod(0o755)
    os.replace(temporary,output)
    print(json.dumps({'file':str(output),'bytes':output.stat().st_size,
        'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'bundled_libraries':len(sources)},indent=2))

if __name__=='__main__':main()
