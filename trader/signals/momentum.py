"""Momentum family — RSI + MACD-histogram + EMA-stack blend, ADX-scaled confidence.

score in [-1,+1]: weighted blend of RSI (centred on 50), MACD histogram (tanh-
normalised by price), and EMA-stack alignment (9/21/50). conf in [0,1]: trend
strength from a Wilder ADX computed in-house.

Truncation-safety: pandas_ta indicators return None on a too-short series (and its
ADX needs ~3*length to emit at all), which would make a bar's value depend on the
frame length rather than on its own history. We therefore coerce every indicator to
a NaN-filled series (compute what is available, per component) and use an own causal
Wilder ADX that emits from ~2*length independent of total length. Each component's
warmup contributes 0, so a bar's score depends only on its own past — the property
the pipeline truncation-invariance test enforces.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta_classic as ta

from . import base, wilder

NAME = "momentum"

RSI_LEN = 14
ADX_LEN = 14
EMA_FAST, EMA_MID, EMA_SLOW = 9, 21, 50
ADX_FULL_CONF = 40.0
MACD_PRICE_SCALE = 0.0005


def _series(x, index) -> pd.Series:
    """Coerce a pandas_ta result (Series or None) to a Series on `index`."""
    if isinstance(x, pd.Series):
        return x.reindex(index)
    return pd.Series(np.nan, index=index)


def populate(df, tf):
    out = df.copy()
    idx = out.index
    close, high, low = out["close"], out["high"], out["low"]

    rsi = _series(ta.rsi(close, length=RSI_LEN), idx)
    rsi_s = ((rsi - 50.0) / 50.0).fillna(0.0)

    macd = ta.macd(close)
    macdh = _series(macd[[c for c in macd.columns if c.startswith("MACDh")][0]], idx) \
        if macd is not None else pd.Series(np.nan, index=idx)
    macd_s = np.tanh(macdh / (close * MACD_PRICE_SCALE)).fillna(0.0)

    ema_f = _series(ta.ema(close, length=EMA_FAST), idx)
    ema_m = _series(ta.ema(close, length=EMA_MID), idx)
    ema_s = _series(ta.ema(close, length=EMA_SLOW), idx)
    stack = ((np.sign(ema_f - ema_m) + np.sign(ema_m - ema_s)) / 2.0).fillna(0.0)

    score = (0.4 * rsi_s + 0.3 * macd_s + 0.3 * stack).clip(-1.0, 1.0)

    adx = wilder.adx(high, low, close, ADX_LEN)
    conf = (adx / ADX_FULL_CONF).clip(0.0, 1.0)

    return base.finalize(out, NAME, score, conf)
