"""Fail-safe primitives — the paper-trading invariants in code form.

Every model/LLM signal reaches the decision path through a flag-file read here,
NEVER a live call on the hot path (guardrail #2). A stale or missing flag → the
neutral default, never a block or a size-up on a missing model. Every reader
returns `(value, error)` and degrades rather than raising.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _parse_ts(ts: Any) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def age_seconds(ts: Any, now: datetime | None = None) -> float | None:
    dt = _parse_ts(ts)
    if dt is None:
        return None
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds()


def read_flag(path: Path, max_age_s: float | None = None,
              ts_field: str = "generated_at", now: datetime | None = None):
    """Read a JSON flag-file. Returns (data, fresh, error).

    - missing/corrupt file  -> (None, False, reason)
    - present but stale      -> (data, False, "stale")   (caller uses neutral)
    - present and fresh      -> (data, True, None)
    Never raises. `fresh` is the only thing a hot-path caller should trust; on
    not-fresh it must fall back to its neutral default.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, False, "missing"
    except Exception as e:  # noqa: BLE001
        return None, False, f"unreadable: {e}"
    if not isinstance(data, dict):
        return None, False, "not an object"
    if max_age_s is not None:
        age = age_seconds(data.get(ts_field), now)
        if age is None:
            return data, False, "no timestamp"
        if age > max_age_s:
            return data, False, "stale"
    return data, True, None


def safe(fn: Callable[[], Any], default: Any = None) -> tuple[Any, str | None]:
    """Run `fn`, returning (result, None) or (default, error-string). Never raises.
    The uniform degrade-don't-crash wrapper for every external reader."""
    try:
        return fn(), None
    except Exception as e:  # noqa: BLE001
        return default, f"{type(e).__name__}: {e}"
