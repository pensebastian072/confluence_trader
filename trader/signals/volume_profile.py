"""Volume profile — POC / VAH / VAL over a trailing window. Leak-safe.

The profile at bar i uses only bars in [i-window+1, i] (past + current, whose
volume is known at its close), so appending future bars never rewrites an earlier
row (truncation-invariant). Prices are bucketed into `bins`; POC is the
highest-volume bucket centre; the value area expands outward from the POC until it
covers `va_pct` of window volume, giving VAH (upper) and VAL (lower).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_WINDOW = 100
DEFAULT_BINS = 24
VA_PCT = 0.70


def value_area(prices: np.ndarray, volumes: np.ndarray, bins: int = DEFAULT_BINS,
               va_pct: float = VA_PCT):
    """(poc, vah, val) for one window. Returns (nan, nan, nan) if degenerate."""
    prices = np.asarray(prices, dtype=float)
    volumes = np.asarray(volumes, dtype=float)
    lo, hi = prices.min(), prices.max()
    if not np.isfinite(lo) or hi <= lo or volumes.sum() <= 0:
        return np.nan, np.nan, np.nan
    edges = np.linspace(lo, hi, bins + 1)
    centres = (edges[:-1] + edges[1:]) / 2.0
    idx = np.clip(np.digitize(prices, edges) - 1, 0, bins - 1)
    vol_by_bin = np.zeros(bins)
    np.add.at(vol_by_bin, idx, volumes)

    poc_i = int(vol_by_bin.argmax())
    total = vol_by_bin.sum()
    target = va_pct * total
    lo_i = hi_i = poc_i
    acc = vol_by_bin[poc_i]
    while acc < target and (lo_i > 0 or hi_i < bins - 1):
        # expand toward the neighbour with more volume
        down = vol_by_bin[lo_i - 1] if lo_i > 0 else -1.0
        up = vol_by_bin[hi_i + 1] if hi_i < bins - 1 else -1.0
        if up >= down:
            hi_i += 1
            acc += max(up, 0.0)
        else:
            lo_i -= 1
            acc += max(down, 0.0)
    return centres[poc_i], centres[hi_i], centres[lo_i]


def rolling_profile(df: pd.DataFrame, window: int = DEFAULT_WINDOW,
                    bins: int = DEFAULT_BINS) -> pd.DataFrame:
    """Add vp_poc / vp_vah / vp_val columns (trailing window, past-only)."""
    out = df.copy()
    typical = ((out["high"] + out["low"] + out["close"]) / 3.0).to_numpy()
    vol = out["volume"].to_numpy(dtype=float)
    n = len(out)
    poc = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    val = np.full(n, np.nan)
    for i in range(window - 1, n):
        s = i - window + 1
        poc[i], vah[i], val[i] = value_area(typical[s:i + 1], vol[s:i + 1], bins)
    out["vp_poc"] = poc
    out["vp_vah"] = vah
    out["vp_val"] = val
    return out
