"""Deterministic synthetic OHLCV generators for signal-family tests.

No randomness unless a seed is passed. Timestamps are tz-aware UTC 1m/5m bars so
frames slot straight into the resample/merge and signal pipelines.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _index(n: int, start: str, freq: str) -> pd.DatetimeIndex:
    return pd.date_range(start=start, periods=n, freq=freq, tz="UTC", name="timestamp")


def ohlc_from_close(close: np.ndarray, spread: float = 0.2, volume=1000,
                    start: str = "2026-01-05 09:30", freq: str = "5min") -> pd.DataFrame:
    """Wrap a close path into an OHLCV frame (high/low = close +/- spread)."""
    close = np.asarray(close, dtype=float)
    n = len(close)
    opens = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame({
        "open": opens,
        "high": close + spread,
        "low": close - spread,
        "close": close,
        "volume": np.full(n, volume, dtype=float),
    }, index=_index(n, start, freq))


def trend(n: int, slope: float, start_price: float = 100.0, noise: float = 0.0,
          seed: int = 0, **kw) -> pd.DataFrame:
    """Linear close trend (+/- optional gaussian noise)."""
    base = start_price + slope * np.arange(n)
    if noise:
        base = base + np.random.RandomState(seed).randn(n) * noise
    return ohlc_from_close(base, **kw)


def from_hl(high, low, **kw) -> pd.DataFrame:
    """Build a frame from explicit high/low arrays (for planted-pivot tests).
    close/open sit at the midpoint."""
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    mid = (high + low) / 2.0
    n = len(high)
    idx = _index(n, kw.get("start", "2026-01-05 09:30"), kw.get("freq", "5min"))
    opens = np.concatenate([[mid[0]], mid[:-1]])
    return pd.DataFrame({"open": opens, "high": high, "low": low,
                         "close": mid, "volume": np.full(n, 1000.0)}, index=idx)
