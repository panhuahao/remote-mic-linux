# SPDX-License-Identifier: GPL-3.0-only
"""Explicit local credential storage; never returned through diagnostic logs."""
import json
import os
import tempfile
from .config import CONFIG

PATH = CONFIG.parent / "youdao-credentials.json"

def read():
    if not PATH.exists():
        return {"app_id": "", "secret": ""}
    value = json.loads(PATH.read_text())
    return {key: str(value.get(key, "")) for key in ("app_id", "secret")}

def save(app_id, secret):
    PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=PATH.parent, prefix=".credentials-")
    try:
        with os.fdopen(fd, "w") as out:
            json.dump({"app_id": app_id.strip(), "secret": secret.strip()}, out)
        os.replace(temporary, PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
