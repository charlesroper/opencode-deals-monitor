"""Atomic JSON and text persistence for state, history, and public outputs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any | None:
    """Load a JSON file. Returns None when the file does not exist."""
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _atomic_write(path: Path, write) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open(encoding="utf-8", mode="w") as fh:
        write(fh)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


def write_json_atomic(path: Path, payload: Any) -> None:
    """Pretty-print JSON with a trailing newline, written atomically."""

    def write(fh) -> None:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    _atomic_write(path, write)


def write_text_atomic(path: Path, text: str) -> None:
    """Write UTF-8 text atomically."""
    _atomic_write(path, lambda fh: fh.write(text))
