"""Parquet bar cache — append-only merge, atomic replace, idempotent.

Layout: data_cache/bars/{SYMBOL}/{tf}.parquet, one file per (symbol, timeframe),
tz-aware UTC DatetimeIndex 'timestamp', columns open/high/low/close/volume.
`merge_upsert` dedups on the index keeping the newest values, so re-running an
update over an overlapping window is a no-op (P1 idempotency requirement).
"""
from __future__ import annotations

import os
import tempfile

import pandas as pd

from .. import config

OHLCV_COLS = ["open", "high", "low", "close", "volume"]


def path_for(symbol: str, tf: str):
    return config.BARS_DIR / symbol.upper() / f"{tf}.parquet"


def load(symbol: str, tf: str) -> pd.DataFrame:
    """Cached bars, or an empty OHLCV frame if none. Never raises."""
    p = path_for(symbol, tf)
    try:
        if p.exists():
            df = pd.read_parquet(p)
            df.index = pd.DatetimeIndex(df.index, name="timestamp")
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            return df.sort_index()
    except Exception:  # noqa: BLE001
        pass
    empty = pd.DataFrame(columns=OHLCV_COLS)
    empty.index = pd.DatetimeIndex([], tz="UTC", name="timestamp")
    return empty


def _atomic_write_parquet(df: pd.DataFrame, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp.parquet")
    os.close(fd)
    try:
        df.to_parquet(tmp)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def merge_upsert(symbol: str, tf: str, new_df: pd.DataFrame) -> dict:
    """Merge new bars into the cache. Returns {added, updated, total}.

    Idempotent: rows with an existing timestamp overwrite in place (newest wins),
    so re-merging the same window changes nothing. Writes only when the merged
    frame differs from what's on disk.
    """
    existing = load(symbol, tf)
    if new_df is None or new_df.empty:
        return {"added": 0, "updated": 0, "total": len(existing)}

    new_df = new_df[[c for c in OHLCV_COLS if c in new_df.columns]].copy()
    new_df.index = pd.DatetimeIndex(new_df.index, name="timestamp")
    if new_df.index.tz is None:
        new_df.index = new_df.index.tz_localize("UTC")
    else:
        new_df.index = new_df.index.tz_convert("UTC")
    new_df = new_df[~new_df.index.duplicated(keep="last")]

    prior_index = existing.index
    updated = int(new_df.index.isin(prior_index).sum())
    added = int(len(new_df) - updated)

    combined = pd.concat([existing, new_df])
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()

    if not combined.equals(existing):
        _atomic_write_parquet(combined, path_for(symbol, tf))
    return {"added": added, "updated": updated, "total": len(combined)}


def last_timestamp(symbol: str, tf: str):
    """Newest cached bar timestamp (tz-aware UTC) or None."""
    df = load(symbol, tf)
    return None if df.empty else df.index.max()


def coverage(symbol: str, tf: str) -> dict:
    df = load(symbol, tf)
    if df.empty:
        return {"symbol": symbol.upper(), "tf": tf, "rows": 0, "start": None, "end": None}
    return {"symbol": symbol.upper(), "tf": tf, "rows": len(df),
            "start": df.index.min().isoformat(), "end": df.index.max().isoformat()}
