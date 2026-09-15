"""Shared swing-pivot engine — the single source of pivots feeding smc_orderflow,
patterns, and fibonacci. Own implementation (no dependency), leak-safe.

A pivot high at bar p (high[p] the strict max of the window [p-left, p+right]) is
CONFIRMED only `right` bars later, at bar p+right — you cannot know a pivot is a
pivot until `right` more bars have printed. We therefore emit the confirmation at
bar p+right, never at p. Because a confirmed pivot depends only on bars <= its
confirmation bar, appending future data never rewrites an earlier value
(truncation-invariant). The last confirmed pivot price is carried forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_LEFT = 2
DEFAULT_RIGHT = 2


def compute(df: pd.DataFrame, left: int = DEFAULT_LEFT,
            right: int = DEFAULT_RIGHT) -> pd.DataFrame:
    """Return `df` copy with swing columns added:

    swing_high_new / swing_low_new : bool, True on the confirmation bar
    swing_high_price / swing_low_price : confirmed pivot price on that bar (else NaN)
    swing_high / swing_low : last confirmed pivot price, carried forward (ffill)
    """
    out = df.copy()
    high = out["high"].to_numpy(dtype=float)
    low = out["low"].to_numpy(dtype=float)
    n = len(out)
    win = left + right + 1

    sh_price = np.full(n, np.nan)
    sl_price = np.full(n, np.nan)
    for i in range(win - 1, n):          # i = confirmation bar
        c = i - right                    # candidate pivot (window centre)
        wh = high[i - win + 1:i + 1]
        wl = low[i - win + 1:i + 1]
        # strict peak at the centre: argmax/argmin land on `left` (first occurrence).
        if wh.argmax() == left and high[c] == wh.max():
            sh_price[i] = high[c]
        if wl.argmin() == left and low[c] == wl.min():
            sl_price[i] = low[c]

    out["swing_high_price"] = sh_price
    out["swing_low_price"] = sl_price
    out["swing_high_new"] = ~np.isnan(sh_price)
    out["swing_low_new"] = ~np.isnan(sl_price)
    out["swing_high"] = pd.Series(sh_price, index=out.index).ffill()
    out["swing_low"] = pd.Series(sl_price, index=out.index).ffill()
    return out
