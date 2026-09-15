"""SMC / order-flow family — market structure (BOS via confirmed swings) + fair
value gaps. Built on the shared swing engine so patterns/fib see the same pivots.

score in [-1,+1]: structural regime (price breaking the last confirmed swing high
-> +1 bullish, last swing low -> -1 bearish, held until the next break) blended
with the latest FVG direction. conf in [0,1]: requires confirmed swings on both
sides, lifted when structure and FVG agree. Leak-safe: confirmed swings and FVGs
are causal, so the family is truncation-invariant.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import base, swings
from ..vendor import smc_fallback

NAME = "smc_orderflow"

STRUCT_W = 0.7
FVG_W = 0.3


def populate(df, tf):
    out = swings.compute(df)
    close = out["close"]

    broke_up = close > out["swing_high"]
    broke_dn = close < out["swing_low"]
    raw = np.select([broke_up.to_numpy(), broke_dn.to_numpy()], [1.0, -1.0], default=np.nan)
    struct = pd.Series(raw, index=out.index).ffill().fillna(0.0)

    fvg = smc_fallback.fair_value_gaps(out)
    out["fvg_dir"] = fvg["fvg_dir"]
    out["fvg_top"] = fvg["fvg_top"]
    out["fvg_bottom"] = fvg["fvg_bottom"]
    fvg_state = fvg["fvg_dir"].replace(0.0, np.nan).ffill().fillna(0.0)

    score = (STRUCT_W * struct + FVG_W * fvg_state).clip(-1.0, 1.0)

    has_both = out["swing_high"].notna() & out["swing_low"].notna()
    agree = (np.sign(struct) == np.sign(fvg_state)) & (struct != 0.0)
    conf = (0.5 + 0.5 * agree.astype(float)) * has_both.astype(float)

    return base.finalize(out, NAME, score, conf)
