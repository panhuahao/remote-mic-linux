#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Build only explicitly releasable sources in an Ubuntu 24.04 container.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
if [ "$#" -ne 2 ]; then
  echo "Usage: $0 /path/to/runtime-x86_64 /path/to/runtime-LICENSE" >&2
  exit 2
fi
runtime=$(realpath -- "$1")
runtime_license=$(realpath -- "$2")
project=$(pwd)
version=$(python3 -c 'import ast,pathlib; tree=ast.parse(pathlib.Path("remote_bridge/__init__.py").read_text()); print(next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="__version__" for t in node.targets)))')
image=${REMOTE_MIC_BUILD_IMAGE:-remote-mic-linux-build:ubuntu24}
base=${REMOTE_MIC_BASE_IMAGE:-ubuntu:24.04}
mirror=${REMOTE_MIC_APT_MIRROR:-http://archive.ubuntu.com/ubuntu}
docker build --network "${REMOTE_MIC_BUILD_NETWORK:-default}" \
  --build-arg "BASE_IMAGE=$base" --build-arg "APT_MIRROR=$mirror" \
  --build-arg "PIP_PROXY=${REMOTE_MIC_PIP_PROXY:-}" \
  -t "$image" -f packaging/ubuntu24/Dockerfile .
python3 scripts/build_release.py
mkdir -p -- "$project/build"
stage=$(mktemp -d "$project/build/ubuntu24-source-XXXXXX")
trap 'rm -rf -- "$stage"' EXIT
tar -xzf "dist/remote-mic-linux-$version-source.tar.gz" --strip-components=1 -C "$stage"
docker run --rm --network=none \
  --mount "type=bind,src=$stage,dst=/src" \
  --mount "type=bind,src=$runtime,dst=/runtime-x86_64,readonly" \
  --mount "type=bind,src=$runtime_license,dst=/runtime-LICENSE,readonly" \
  "$image" bash -ec '
    python -m unittest discover -s tests -q
    python scripts/build_appimage.py --runtime /runtime-x86_64 --runtime-license /runtime-LICENSE
    python scripts/build_deb.py
    ./build/RemoteMicLinux.AppDir/AppRun --self-test
  '
cp -- "$stage/dist/Remote-Mic-Linux-$version-x86_64.AppImage" "dist/"
cp -- "$stage/dist/remote-mic-linux_${version}_amd64.deb" "dist/"
# The generated AppDir is retained for independent ABI and desktop validation.
python3 - "$stage/build/RemoteMicLinux.AppDir" <<'PY'
from pathlib import Path
import shutil,sys
source=Path(sys.argv[1])
target=Path('build/RemoteMicLinux.AppDir')
if target.exists():shutil.rmtree(target)
shutil.copytree(source,target,symlinks=True)
PY
python3 scripts/build_release.py
(cd dist && sha256sum -c SHA256SUMS)
