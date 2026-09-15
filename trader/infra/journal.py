"""Append-only JSONL journal + atomic JSON state. Shapes ported from
robinhood_desk/desk/ticket_builder.py (write_state / append_jsonl / read).

Journal lines are append-only: callers append event records, never rewrite
existing lines. State files are replaced atomically (tmp + os.replace).
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    """All records; corrupt/blank lines skipped. Missing file -> []."""
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    except FileNotFoundError:
        pass
    except Exception:  # noqa: BLE001
        pass
    return out


def write_state(path: Path, state: dict) -> None:
    """Atomic write (tmp + os.replace). Stamps `as_of` (UTC ISO)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    state = dict(state)
    state["as_of"] = datetime.now(timezone.utc).isoformat()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_state(path: Path, default: dict | None = None) -> dict:
    """Read a JSON state file; missing/corrupt -> default (or {})."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:  # noqa: BLE001
        pass
    return dict(default) if default else {}
