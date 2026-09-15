"""Resample base-TF (1m) OHLCV to higher timeframes — the ONE resampler.

Convention (fixed here, unit-tested, never changed silently — PLAN.md risk item):
a higher-TF bar labeled `t` aggregates base bars in the half-open interval
`[t, t + tf)` (pandas closed='left', label='left'), matching Alpaca's
START-labeled bars. So the bar's timestamp is its OPEN; its CLOSE (and thus the
moment its values become known) is `t + tf`. The merge layer uses that close time
for no-look-ahead alignment.

OHLCV aggregation: open=first, high=max, low=min, close=last, volume=sum. Empty
buckets (gaps / overnight) are dropped.
"""
from __future__ import annotations

import pandas as pd

# Higher TF -> (pandas offset alias, bar duration).
_RULE = {
    "5m": ("5min", pd.Timedelta(minutes=5)),
    "15m": ("15min", pd.Timedelta(minutes=15)),
    "1h": ("1h", pd.Timedelta(hours=1)),
    "4h": ("4h", pd.Timedelta(hours=4)),
}

_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def tf_delta(tf: str) -> pd.Timedelta:
    if tf not in _RULE:
        raise ValueError(f"unsupported higher timeframe {tf!r}")
    return _RULE[tf][1]


def resample(df_1m: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Aggregate 1m OHLCV up to `tf`. Start-labeled, half-open [t, t+tf)."""
    if tf not in _RULE:
        raise ValueError(f"unsupported higher timeframe {tf!r}")
    rule, _ = _RULE[tf]
    if df_1m.empty:
        return df_1m.copy()
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in df_1m.columns]
    out = (df_1m[cols]
           .resample(rule, label="left", closed="left")
           .agg({c: _AGG[c] for c in cols})
           .dropna(subset=["open"]))
    out.index.name = "timestamp"
    return out
