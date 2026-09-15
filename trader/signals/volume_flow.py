"""Volume/flow family — anchored VWAP, MFI, OBV flow-trend; relative-volume conf,
plus POC/VAH/VAL levels attached for downstream target-snapping.

score in [-1,+1]: blend of price-vs-session-VWAP (tanh), MFI (centred on 50), and
OBV flow-trend (a lightweight divergence proxy — flow momentum vs price). conf in
[0,1]: relative volume (participation) with a warmup floor. All same-feed relative:
IEX volume is a small slice of consolidated, so every term is self-referential.
"""
from __future__ import annotations

import numpy as np
import pandas_ta_classic as ta

from . import base, volume_profile

NAME = "volume_flow"

MFI_LEN = 14
OBV_LOOKBACK = 10
RELVOL_LEN = 20
RELVOL_FULL = 2.0        # 2x average volume -> conf 1.0
VWAP_SCALE = 0.001       # price * this normalises the VWAP distance


def populate(df, tf):
    out = df.copy()
    high, low, close, vol = out["high"], out["low"], out["close"], out["volume"]

    vwap = ta.vwap(high, low, close, vol)
    vwap_s = np.tanh((close - vwap) / (close * VWAP_SCALE)) if vwap is not None else 0.0

    mfi = ta.mfi(high, low, close, vol, length=MFI_LEN)
    mfi_s = ((mfi - 50.0) / 50.0) if mfi is not None else 0.0

    obv = ta.obv(close, vol)
    if obv is not None:
        scale = obv.abs().rolling(RELVOL_LEN).mean().replace(0, np.nan)
        obv_s = np.tanh(obv.diff(OBV_LOOKBACK) / scale)
    else:
        obv_s = 0.0

    score = (0.4 * vwap_s + 0.3 * mfi_s + 0.3 * obv_s)

    relvol = vol / vol.rolling(RELVOL_LEN).mean()
    conf = (relvol / RELVOL_FULL).clip(0.0, 1.0)

    # attach value-area levels (leak-safe rolling) for downstream snapping.
    out = volume_profile.rolling_profile(out)
    return base.finalize(out, NAME, score, conf)
