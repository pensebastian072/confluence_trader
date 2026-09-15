"""P2 leakage suite — resample + no-look-ahead merge. The hard gate for every
later phase. All network-free / deterministic.
"""
from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from trader.mtf import merge, resample


def _synth1m(n: int, start: str = "2026-01-05 09:30") -> pd.DataFrame:
    idx = pd.date_range(start=start, periods=n, freq="1min", tz="UTC", name="timestamp")
    i = range(n)
    return pd.DataFrame({
        "open": [100.0 + k for k in i],
        "high": [100.5 + k for k in i],   # strictly increasing -> distinct bucket highs
        "low": [99.5 + k for k in i],
        "close": [100.2 + k for k in i],
        "volume": [10 + k for k in i],
    }, index=idx)


# ── resample ─────────────────────────────────────────────────────────
def test_resample_ohlcv_agg():
    df = _synth1m(10)                       # 09:30..09:39
    r = resample.resample(df, "5m")
    assert list(r.index) == [df.index[0], df.index[5]]   # start-labeled: 09:30, 09:35
    b0 = r.iloc[0]
    assert b0["open"] == df.iloc[0]["open"]              # first
    assert b0["high"] == df.iloc[:5]["high"].max()       # max of bucket
    assert b0["low"] == df.iloc[:5]["low"].min()         # min
    assert b0["close"] == df.iloc[4]["close"]            # last
    assert b0["volume"] == df.iloc[:5]["volume"].sum()   # sum


def test_resample_empty_and_bad_tf():
    assert resample.resample(_synth1m(0), "5m").empty
    with pytest.raises(ValueError):
        resample.resample(_synth1m(5), "3m")


# ── merge: golden visibility (no look-ahead) ─────────────────────────
def test_merge_no_lookahead_visibility():
    df = _synth1m(11)                       # 09:30..09:40
    r5 = resample.resample(df, "5m")        # buckets 09:30 (close 09:35), 09:35 (close 09:40)
    m = merge.merge_informative(df, r5, "5m")
    ts = df.index
    # before the first bucket closes -> NaN (no completed higher bar yet)
    assert pd.isna(m.loc[ts[4], "5m_high"])            # 09:34 < 09:35 close
    # at/after close -> sees the COMPLETED 09:30 bucket, not the forming one
    assert m.loc[ts[5], "5m_high"] == r5.iloc[0]["high"]   # 09:35
    assert m.loc[ts[9], "5m_high"] == r5.iloc[0]["high"]   # 09:39 still bucket-0
    # 09:40 = close of the 09:35 bucket -> now visible
    assert m.loc[ts[10], "5m_high"] == r5.iloc[1]["high"]  # 09:40


def test_merge_carries_forward_until_next_close():
    df = _synth1m(20)
    r5 = resample.resample(df, "5m")
    m = merge.merge_informative(df, r5, "5m")
    # rows 09:35..09:39 all carry bucket-0 (ffill via asof backward)
    vals = m.iloc[5:10]["5m_close"].unique()
    assert len(vals) == 1 and vals[0] == r5.iloc[0]["close"]


# ── truncation-invariance (the leakage killer) ───────────────────────
@pytest.mark.parametrize("k", [7, 13, 20, 33, 50])
def test_truncation_invariance(k):
    base = _synth1m(60)
    full = merge.build_mtf_frame(base, ("5m", "15m"))
    trunc = merge.build_mtf_frame(base.iloc[:k], ("5m", "15m"))
    # every row present in the truncated build must be bit-identical in the full build
    assert_frame_equal(full.loc[trunc.index], trunc, check_freq=False)


def test_build_mtf_frame_columns():
    base = _synth1m(30)
    out = merge.build_mtf_frame(base, ("5m", "15m"))
    for tf in ("5m", "15m"):
        for c in ("open", "high", "low", "close", "volume"):
            assert f"{tf}_{c}" in out.columns
    assert len(out) == len(base)            # base rows preserved 1:1
