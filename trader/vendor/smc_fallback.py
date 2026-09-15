"""Vendored Smart-Money-Concepts primitives — the day-1 fallback that became the
primary path (smartmoneyconcepts==0.0.26 hard-pins pandas==2.0.2, incompatible with
this repo's pandas>=2.2). Own implementation so leak-safety is guaranteed.

All primitives are causal: they use only the current and prior bars, so a value at
bar i never changes when future bars are appended (truncation-invariant).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def fair_value_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """3-candle fair value gaps, detected on the third candle (bar i).

    Bullish FVG: candle i-2 high < candle i low (unfilled gap up).
    Bearish FVG: candle i-2 low  > candle i high (gap down).
    Returns fvg_dir (+1/-1/0 at formation), fvg_top, fvg_bottom (gap bounds).
    """
    high, low = df["high"], df["low"]
    prev2_high, prev2_low = high.shift(2), low.shift(2)
    bull = low > prev2_high
    bear = high < prev2_low
    direction = np.select([bull, bear], [1.0, -1.0], default=0.0)
    top = np.where(bull, low, np.where(bear, prev2_low, np.nan))
    bottom = np.where(bull, prev2_high, np.where(bear, high, np.nan))
    return pd.DataFrame({"fvg_dir": direction, "fvg_top": top, "fvg_bottom": bottom},
                        index=df.index)
