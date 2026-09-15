"""Regime classifier — trend / chop / transitional from ADX + ATR percentile.

Regime keys the scorer's weight preset (config.REGIME_WEIGHTS). Causal: ADX and the
rolling ATR-percentile use only past/current bars, so a bar's regime never changes
when future data is appended. Warmup rows resolve to the default regime.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config
from ..signals import wilder

ADX_LEN = 14
ATR_LEN = 14
ATR_PCTL_WINDOW = 100
ADX_TREND = 25.0
ADX_CHOP = 20.0


def classify(df: pd.DataFrame) -> pd.Series:
    """Per-bar regime label. Returns a Series aligned to df.index.

    ADX/ATR are the in-house causal Wilder versions (not pandas_ta), so a bar's
    regime — and thus the scorer weights it selects — depends only on its own
    history and is truncation-invariant even on short frames."""
    high, low, close = df["high"], df["low"], df["close"]
    adx = wilder.adx(high, low, close, length=ADX_LEN)
    atr = wilder.atr(high, low, close, length=ATR_LEN)

    n = len(df)

    # ATR percentile within a trailing window (rank of the last value, 0..1).
    atr_pctl = atr.rolling(ATR_PCTL_WINDOW).apply(
        lambda w: (w <= w[-1]).mean(), raw=True)

    adx_v = adx.to_numpy()
    pctl_v = atr_pctl.to_numpy()
    out = np.full(n, config.DEFAULT_REGIME, dtype=object)
    for i in range(n):
        a = adx_v[i]
        if np.isnan(a):
            continue
        if a >= ADX_TREND:
            out[i] = "trend"
        elif a < ADX_CHOP and (np.isnan(pctl_v[i]) or pctl_v[i] < 0.5):
            out[i] = "chop"
        else:
            out[i] = "transitional"
    return pd.Series(out, index=df.index)
