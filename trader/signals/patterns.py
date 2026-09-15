"""Patterns family — own swing-pivot geometry. Fires on COMPLETION only.

v1 implements the two highest-signal reversals: double top (bearish) and double
bottom (bullish), completing when price breaks the intervening neckline. A
completed pattern's direction decays over ~20 bars. Built on confirmed swings, so
detection is causal and truncation-invariant.

TODO (documented follow-up, tracked in PLAN.md): head-and-shoulders, triangles, and
multi-touch S/R zones. The family already returns a valid bounded (0,0)-safe score
without them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import base, swings

NAME = "patterns"

PRICE_TOL = 0.005     # two extremes "equal" within 0.5%
PATTERN_EXPIRY = 50   # bars a pending neckline stays armed
DECAY_BARS = 20       # a completed signal decays after this many bars


def populate(df, tf):
    out = swings.compute(df)
    n = len(out)
    close = out["close"].to_numpy()
    sh_new = out["swing_high_new"].to_numpy()
    sl_new = out["swing_low_new"].to_numpy()
    sh_price = out["swing_high_price"].to_numpy()
    sl_price = out["swing_low_price"].to_numpy()

    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    pending: list[dict] = []
    pattern = np.zeros(n)

    for i in range(n):
        if sh_new[i]:
            highs.append((i, sh_price[i]))
            if len(highs) >= 2:
                (p1, v1), (p2, v2) = highs[-2], highs[-1]
                if v1 > 0 and abs(v2 - v1) / v1 < PRICE_TOL:
                    troughs = [lp for (lpos, lp) in lows if p1 < lpos < p2]
                    if troughs:
                        pending.append({"dir": -1.0, "neck": min(troughs), "exp": i + PATTERN_EXPIRY})
        if sl_new[i]:
            lows.append((i, sl_price[i]))
            if len(lows) >= 2:
                (p1, v1), (p2, v2) = lows[-2], lows[-1]
                if v1 > 0 and abs(v2 - v1) / v1 < PRICE_TOL:
                    peaks = [hp for (hpos, hp) in highs if p1 < hpos < p2]
                    if peaks:
                        pending.append({"dir": 1.0, "neck": max(peaks), "exp": i + PATTERN_EXPIRY})

        still = []
        for pat in pending:
            if i > pat["exp"]:
                continue
            if pat["dir"] < 0 and close[i] < pat["neck"]:
                pattern[i] = -1.0     # double top completed (break below neckline)
            elif pat["dir"] > 0 and close[i] > pat["neck"]:
                pattern[i] = 1.0      # double bottom completed
            else:
                still.append(pat)
        pending = still

    state = pd.Series(pattern, index=out.index).replace(0.0, np.nan).ffill(limit=DECAY_BARS).fillna(0.0)
    conf = (state != 0.0).astype(float) * 0.5
    return base.finalize(out, NAME, state, conf)
