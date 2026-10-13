"""Shared filesystem operations for configurations and private state."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, text: str, *, mode: int = 0o600) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            os.fchmod(fp.fileno(), mode)
            fp.write(text)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_write_json(path: Path, value: Any) -> None:
    # Serialize before opening the destination, including for plugin variables.
    text = json.dumps(value, ensure_ascii=False, indent=2)
    atomic_write_text(path, text + "\n")


def config_digest(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def task_path(root: Path, name: str) -> Path:
    if (
        not name
        or name != name.strip()
        or name in {".", ".."}
        or any(char in name for char in "/\\")
        or any(ord(char) < 32 for char in name)
    ):
        raise ValueError("任务名称不能为空，也不能包含目录分隔符、控制字符或相对路径")
    root = Path(root)
    target = root / name
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("任务目录不能指向工作目录之外")
    return target
