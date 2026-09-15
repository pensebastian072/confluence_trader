"""Causal Wilder-smoothed indicators — ATR / ADX / RMA.

Own implementations because pandas_ta returns None on a too-short series and its ADX
needs ~3*length to emit at all, which makes a bar's value depend on total frame
length rather than its own history — a truncation-invariance hazard. These emit from
their natural warmup, seeded at the first bar, so a bar depends only on its own past.
Shared by the momentum family, the regime classifier, and the pipeline ATR.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rma(s: pd.Series, length: int) -> pd.Series:
    """Wilder's smoothing (recursive EMA, alpha=1/length), seeded at the first bar."""
    return s.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat([(high - low), (high - prev_close).abs(),
                      (low - prev_close).abs()], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    return rma(true_range(high, low, close), length)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    up = high.diff()
    dn = -low.diff()
    plus_dm = ((up > dn) & (up > 0)) * up.clip(lower=0)
    minus_dm = ((dn > up) & (dn > 0)) * dn.clip(lower=0)
    atr_ = rma(true_range(high, low, close), length)
    pdi = 100 * rma(plus_dm, length) / atr_
    mdi = 100 * rma(minus_dm, length) / atr_
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return rma(dx, length)
