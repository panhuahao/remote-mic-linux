# SPDX-License-Identifier: GPL-3.0-only
"""Recover the host environment before starting programs outside the bundle."""
import os


# Keep this list aligned with AppRun. Do not strip arbitrary user environment
# variables: desktop sessions, proxy settings and credentials belong to users.
_BUNDLE_VARIABLES = (
    "PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE",
    "LD_LIBRARY_PATH", "GI_TYPELIB_PATH", "GDK_PIXBUF_MODULE_FILE",
    "GTK_IM_MODULE_FILE", "GIO_MODULE_DIR", "APPDIR", "APPIMAGE", "OWD",
    "REMOTE_MIC_BUNDLE",
)
_HOST_VARIABLES = {
    "PATH": "REMOTE_MIC_HOST_PATH",
    "XDG_DATA_DIRS": "REMOTE_MIC_HOST_XDG_DATA_DIRS",
    "GDK_BACKEND": "REMOTE_MIC_HOST_GDK_BACKEND",
}
# Unlike the optional XDG/backend defaults above, an explicitly empty module
# variable must stay empty when returning to the host. Backup presence records
# whether the user originally set the variable at all.
_HOST_MODULE_VARIABLES = {
    "GTK_MODULES": "REMOTE_MIC_HOST_GTK_MODULES",
    "GTK_PATH": "REMOTE_MIC_HOST_GTK_PATH",
    "GIO_EXTRA_MODULES": "REMOTE_MIC_HOST_GIO_EXTRA_MODULES",
}


def host_environment(environment=None):
    """Return a copy suitable for a host subprocess or desktop launch context.

    Source installations already use the host runtime. AppRun saves the
    desktop's PATH, data search path and chosen GTK backend before replacing
    them; empty optional backups mean the variable was unset/defaulted.
    """
    environment = os.environ if environment is None else environment
    result = dict(environment)
    if environment.get("REMOTE_MIC_BUNDLE") != "1":
        return result
    for name in _BUNDLE_VARIABLES:
        result.pop(name, None)
    for name, backup in _HOST_VARIABLES.items():
        value = result.pop(backup, None)
        if value is not None and (value or name == "PATH"):
            result[name] = value
        elif name == "PATH":
            # An older/incomplete launcher must never resolve a host tool
            # through the private bundle bin directory.
            result[name] = os.defpath
        else:
            result.pop(name, None)
    for name, backup in _HOST_MODULE_VARIABLES.items():
        if backup in result:
            result[name] = result.pop(backup)
        else:
            result.pop(name, None)
    return result
