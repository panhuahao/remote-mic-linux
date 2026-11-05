#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-only
# Destructive package lifecycle test for a disposable container, never the host.
set -Eeuo pipefail

if [[ "${REMOTE_MIC_DISPOSABLE_TEST:-}" != "1" ]]; then
    printf '%s\n' 'Refusing to install: set REMOTE_MIC_DISPOSABLE_TEST=1 inside a disposable container.' >&2
    exit 2
fi
if [[ ! -e /.dockerenv && ! -e /run/.containerenv ]]; then
    printf '%s\n' 'Refusing to install: Docker/Podman container marker is missing.' >&2
    exit 2
fi
if [[ "$(id -u)" != "0" ]]; then
    printf '%s\n' 'This disposable-container test must run as root to exercise apt install/remove/purge.' >&2
    exit 2
fi
if [[ "$#" != 1 || "$1" != /* || ! -f "$1" ]]; then
    printf '%s\n' 'Usage: REMOTE_MIC_DISPOSABLE_TEST=1 scripts/check_deb_install.sh /absolute/path/package.deb' >&2
    exit 2
fi
for dependency in apt-get dpkg dpkg-query dpkg-deb runuser useradd userdel sha256sum; do
    if ! command -v "$dependency" >/dev/null; then
        printf 'Missing test dependency: %s\n' "$dependency" >&2
        exit 2
    fi
done

deb_path=$(readlink -f -- "$1")
package_name=$(dpkg-deb --field "$deb_path" Package)
package_version=$(dpkg-deb --field "$deb_path" Version)
package_architecture=$(dpkg-deb --field "$deb_path" Architecture)
if [[ "$package_name" != "remote-mic-linux" || "$package_architecture" != "amd64" ||
      ! "$package_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.+~][a-zA-Z0-9]+)*$ ]]; then
    printf '%s\n' 'The test accepts only a versioned remote-mic-linux amd64 package.' >&2
    exit 2
fi
if [[ "$(dpkg --print-architecture)" != "$package_architecture" ]]; then
    printf '%s\n' 'Container architecture does not match the package.' >&2
    exit 2
fi
if [[ "$(dpkg-query --show --showformat='${db:Status-Status}' "$package_name" 2>/dev/null || true)" == "installed" ]]; then
    printf '%s\n' 'Refusing to replace an existing installation; start a fresh disposable container.' >&2
    exit 2
fi
read -r package_sha256 _ < <(sha256sum -- "$deb_path")

test_directory=$(mktemp -d /tmp/remote-mic-lifecycle.XXXXXXXX)
test_user="remote-mic-test-$$"
test_home="$test_directory/home"
test_log="$test_directory/commands.log"
test_step='prepare'
created_user=0
cleanup() {
    local exit_status=$?
    trap - EXIT
    if [[ "$exit_status" != 0 ]]; then
        printf 'DEB lifecycle check failed at: %s\n' "$test_step" >&2
        if [[ -f "$test_log" ]]; then tail -n 100 "$test_log" >&2; fi
    fi
    if [[ "$created_user" == 1 ]]; then userdel "$test_user" >/dev/null 2>&1 || true; fi
    if [[ "$test_directory" == /tmp/remote-mic-lifecycle.* ]]; then rm -rf -- "$test_directory"; fi
    exit "$exit_status"
}
trap cleanup EXIT
chmod 0755 "$test_directory"
mkdir -p "$test_home"
useradd --system --no-create-home --home-dir "$test_home" --shell /bin/sh "$test_user"
created_user=1
chown "$test_user" "$test_home"
chmod 0700 "$test_home"

as_test_user() {
    runuser -u "$test_user" -- env -i \
        PATH=/usr/bin:/bin HOME="$test_home" USER="$test_user" LOGNAME="$test_user" \
        XDG_CONFIG_HOME="$test_home/.config" XDG_CACHE_HOME="$test_home/.cache" \
        XDG_DATA_HOME="$test_home/.local/share" XDG_RUNTIME_DIR="$test_home/runtime" \
        "$@"
}

assert_user_data() {
    as_test_user /bin/sh -eu -c '
        test "$(cat "$HOME/.config/ubuntu-remote-bridge/config.json")" = "config-sentinel"
        test "$(cat "$HOME/.config/ubuntu-remote-bridge/youdao-credentials.json")" = "credential-sentinel-no-real-key"
        test "$(cat "$HOME/.cache/ubuntu-remote-bridge/sensevoice/model.int8.onnx")" = "model-sentinel-not-a-model"
        test -w "$HOME/.config/ubuntu-remote-bridge/config.json"
        test -w "$HOME/.cache/ubuntu-remote-bridge/sensevoice/model.int8.onnx"
    '
}

assert_system_files_removed() {
    test ! -e /usr/bin/remote-mic-linux
    test ! -e /usr/lib/remote-mic-linux
    test ! -e /usr/share/applications/io.github.panhuahao.RemoteMicLinux.desktop
    test ! -e /usr/share/icons/hicolor/scalable/apps/remote-mic-linux.svg
    test ! -e /usr/share/icons/hicolor/64x64/apps/remote-mic-linux.png
    test ! -e /usr/share/icons/hicolor/256x256/apps/remote-mic-linux.png
    test ! -e /usr/share/icons/hicolor/512x512/apps/remote-mic-linux.png
    test ! -e /usr/share/doc/remote-mic-linux
}

test_step='install'
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    "$deb_path" desktop-file-utils >>"$test_log" 2>&1
test "$(dpkg-query --show --showformat='${Version}' "$package_name")" = "$package_version"
test -x /usr/bin/remote-mic-linux
test -x /usr/lib/remote-mic-linux/AppRun
desktop-file-validate /usr/share/applications/io.github.panhuahao.RemoteMicLinux.desktop >>"$test_log" 2>&1

test_step='non-root-runtime'
as_test_user mkdir -p "$test_home/runtime"
as_test_user chmod 0700 "$test_home/runtime"
test "$(as_test_user id -u)" != 0
as_test_user test ! -w /usr/bin/remote-mic-linux
as_test_user test ! -w /usr/lib/remote-mic-linux/AppRun
as_test_user test ! -w /usr/lib/remote-mic-linux/app/remote_bridge/__init__.py
test "$(as_test_user /usr/bin/remote-mic-linux --version)" = "Remote Mic Linux $package_version"
as_test_user /usr/bin/remote-mic-linux --self-test >>"$test_log" 2>&1

test_step='create-user-data-sentinels'
as_test_user /bin/sh -eu -c '
    umask 077
    mkdir -p "$HOME/.config/ubuntu-remote-bridge" "$HOME/.cache/ubuntu-remote-bridge/sensevoice"
    printf "%s" config-sentinel > "$HOME/.config/ubuntu-remote-bridge/config.json"
    printf "%s" credential-sentinel-no-real-key > "$HOME/.config/ubuntu-remote-bridge/youdao-credentials.json"
    printf "%s" model-sentinel-not-a-model > "$HOME/.cache/ubuntu-remote-bridge/sensevoice/model.int8.onnx"
'
assert_user_data

test_step='same-version-reinstall'
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends --reinstall \
    "$deb_path" >>"$test_log" 2>&1
test "$(dpkg-query --show --showformat='${Version}' "$package_name")" = "$package_version"
test "$(as_test_user /usr/bin/remote-mic-linux --version)" = "Remote Mic Linux $package_version"
as_test_user /usr/bin/remote-mic-linux --self-test >>"$test_log" 2>&1
assert_user_data

test_step='remove'
DEBIAN_FRONTEND=noninteractive apt-get remove -y "$package_name" >>"$test_log" 2>&1
assert_system_files_removed
assert_user_data

# A package without conffiles disappears from dpkg after removal. Reinstall the
# local file so purge exercises an installed package even without an apt index.
test_step='reinstall-for-purge'
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    "$deb_path" >>"$test_log" 2>&1
test "$(dpkg-query --show --showformat='${Version}' "$package_name")" = "$package_version"
test "$(as_test_user /usr/bin/remote-mic-linux --version)" = "Remote Mic Linux $package_version"
assert_user_data

test_step='purge'
DEBIAN_FRONTEND=noninteractive apt-get purge -y "$package_name" >>"$test_log" 2>&1
assert_system_files_removed
assert_user_data
test "$(dpkg-query --show --showformat='${db:Status-Status}' "$package_name" 2>/dev/null || true)" != installed

printf '{"package":"%s","version":"%s","architecture":"%s","sha256":"%s","install":"passed","non_root_version":"passed","non_root_self_test":"passed","desktop_validation":"passed","same_version_reinstall":"passed","remove":"passed","reinstall_for_purge":"passed","purge":"passed","user_data_preserved":"passed","system_files_removed":"passed","cross_version_upgrade":"not_tested","bluetooth_audio_desktop_session":"not_tested"}\n' \
    "$package_name" "$package_version" "$package_architecture" "$package_sha256"
