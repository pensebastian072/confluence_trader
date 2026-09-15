"""Fibonacci family — retracement grid + extensions off the last completed swing
leg (shared swing engine). Levels are attached for downstream target snapping.

The active leg runs between the most-recent confirmed swing high and low. In an
up-leg (low -> high) a healthy pullback into the .382-.786 band — richest at the
.618 golden pocket — is a bullish continuation signal; a down-leg mirrors it. A
smooth triangular kernel centred on .618 gives the score magnitude. Leak-safe:
built only from confirmed (causal) swings, so truncation-invariant.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import base, swings

NAME = "fibonacci"

RATIOS = (0.382, 0.5, 0.618, 0.786)
EXTS = (1.272, 1.618)
KERNEL_CENTER = 0.618
KERNEL_WIDTH = 0.4


def populate(df, tf):
    out = swings.compute(df)
    hi = out["swing_high"]
    lo = out["swing_low"]
    close = out["close"]

    # direction of the most recent confirmed pivot (+1 high, -1 low), carried fwd.
    last_dir = pd.Series(np.where(out["swing_high_new"], 1.0,
                                  np.where(out["swing_low_new"], -1.0, np.nan)),
                         index=out.index).ffill()

    rng = (hi - lo)
    valid = rng > 0

    # retracement fraction from the leg extreme (0 at the extreme, 1 at the origin).
    retr_up = (hi - close) / rng      # up-leg: measured down from the high
    retr_dn = (close - lo) / rng      # down-leg: measured up from the low
    retr = np.where(last_dir > 0, retr_up, retr_dn)

    prox = np.clip(1.0 - np.abs(retr - KERNEL_CENTER) / KERNEL_WIDTH, 0.0, 1.0)
    in_leg = valid & (retr >= 0) & (retr <= 1.0)
    score = np.where(in_leg, last_dir * prox, 0.0)
    conf = np.where(in_leg & (last_dir != 0), 0.4 + 0.2 * prox, 0.0)

    # levels (up-leg measured from high; down-leg from low). Attached for snapping.
    for r in RATIOS:
        up = hi - r * rng
        dn = lo + r * rng
        out[f"fib_{int(r * 1000)}"] = np.where(last_dir > 0, up, dn)
    for e in EXTS:
        up = hi + (e - 1.0) * rng
        dn = lo - (e - 1.0) * rng
        out[f"fib_ext_{int(e * 1000)}"] = np.where(last_dir > 0, up, dn)

    return base.finalize(out, NAME, score, conf)
