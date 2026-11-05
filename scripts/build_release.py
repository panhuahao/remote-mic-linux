#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build source-only archives from an explicit public-file allowlist."""
import ast
import gzip
import hashlib
import io
from pathlib import Path
import re
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'README.md', 'README.en.md', '.dockerignore', 'packaging/ubuntu24/Dockerfile', 'scripts/build_ubuntu24.sh', 'scripts/check_deb_install.sh', 'LICENSE.md', 'SOURCES.md', 'CHANGELOG.md',
    'CONTRIBUTING.md', 'RELEASE.md', '.gitignore', 'requirements.txt',
    'config.example.json', 'run.sh', 'install.sh', 'install_model.py',
    'install_desktop.py', 'ui-preview.png', 'remote_bridge/theme.css',
)
TREES = {'remote_bridge': '*.py', 'tests': '*.py', 'scripts': '*.py',
         '.github/workflows': '*.yml', 'docs': '*.md'}

def main():
    module = ast.parse((ROOT/'remote_bridge/__init__.py').read_text())
    version = next(ast.literal_eval(n.value) for n in module.body
                   if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == '__version__' for t in n.targets))
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:[-.][a-zA-Z0-9]+)*', version):
        raise ValueError('Invalid release version')
    paths = [ROOT/p for p in FILES]
    for directory, pattern in TREES.items():
        paths.extend(sorted((ROOT/directory).rglob(pattern)))
    paths.extend(p for p in sorted((ROOT/'assets').rglob('*')) if p.suffix in ('.svg','.png','.txt'))
    paths = sorted(set(paths))
    for path in paths:
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError('Missing or unsafe release file: '+str(path.relative_to(ROOT)))
    stem = f'remote-mic-linux-{version}-source'
    out = ROOT/'dist'
    out.mkdir(exist_ok=True)
    manifest = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT).as_posix()}\n' for p in paths).encode()
    entries = [(p.relative_to(ROOT).as_posix(), p.read_bytes(), 0o755 if p.suffix == '.sh' else 0o644) for p in paths]
    entries.append(('MANIFEST.sha256', manifest, 0o644))
    with (out/(stem+'.tar.gz')).open('wb') as raw:
        with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode='w') as tar:
                for name, data, mode in entries:
                    info = tarfile.TarInfo(stem+'/'+name)
                    info.size = len(data); info.mode = mode
                    info.uid = info.gid = info.mtime = 0
                    info.uname = info.gname = ''
                    tar.addfile(info, io.BytesIO(data))
    with zipfile.ZipFile(out/(stem+'.zip'), 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data, mode in entries:
            info = zipfile.ZipInfo(stem+'/'+name, date_time=(1980,1,1,0,0,0))
            info.create_system = 3
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    archives = [out/(stem+s) for s in ('.tar.gz','.zip')]
    archives.extend(sorted(out.glob(f'Remote-Mic-Linux-{version}-*.AppImage')))
    archives.extend(sorted(out.glob(f'remote-mic-linux_{version}_*.deb')))
    (out/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in archives))
    print(f'Built {len(paths)} public files into source archives:')
    for p in archives:
        print(f'  {p.name} ({p.stat().st_size} bytes)')
    print('Excluded runtime, models, recordings, logs and user credentials.')

if __name__ == '__main__':
    main()
