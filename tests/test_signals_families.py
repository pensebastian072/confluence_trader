"""P3 family tests — volume_flow, volume_profile, smc_orderflow + FVG. Network-free."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trader.signals import base, smc_orderflow, volume_flow, volume_profile
from trader.vendor import smc_fallback
from tests.fixtures import synthetic as syn


# ── volume_profile ───────────────────────────────────────────────────
def test_value_area_poc_and_bounds():
    # heavy volume clustered near price 100, thin tails.
    prices = np.array([90, 95, 100, 100, 100, 100, 105, 110], dtype=float)
    volumes = np.array([1, 1, 50, 50, 50, 50, 1, 1], dtype=float)
    poc, vah, val = volume_profile.value_area(prices, volumes, bins=8)
    assert val <= poc <= vah
    assert 98 <= poc <= 102          # POC sits on the 100 cluster


def test_value_area_degenerate():
    flat = np.full(10, 100.0)
    poc, vah, val = volume_profile.value_area(flat, np.ones(10))
    assert np.isnan(poc) and np.isnan(vah) and np.isnan(val)


@pytest.mark.parametrize("k", [40, 60, 80])
def test_rolling_profile_truncation_invariant(k):
    df = syn.trend(90, 0.1, noise=1.0, seed=5)
    full = volume_profile.rolling_profile(df, window=30, bins=12)
    trunc = volume_profile.rolling_profile(df.iloc[:k], window=30, bins=12)
    cols = ["vp_poc", "vp_vah", "vp_val"]
    a = full.loc[trunc.index, cols].fillna(-1).to_numpy()
    b = trunc[cols].fillna(-1).to_numpy()
    assert np.allclose(a, b, atol=1e-9)


# ── volume_flow ──────────────────────────────────────────────────────
def test_volume_flow_bounds_and_warmup():
    out = base.run_family(volume_flow, syn.trend(120, 0.1, noise=0.5, seed=1), "5m")
    sc, cf = out["f_volume_flow_score"], out["f_volume_flow_conf"]
    assert sc.between(-1, 1).all() and cf.between(0, 1).all()
    assert sc.iloc[0] == 0.0 and cf.iloc[0] == 0.0


def test_volume_flow_uptrend_positive():
    out = base.run_family(volume_flow, syn.trend(120, 0.2), "5m")
    assert out["f_volume_flow_score"].iloc[-1] > 0.0


@pytest.mark.parametrize("k", [70, 100])
def test_volume_flow_truncation_invariant(k):
    df = syn.trend(120, 0.12, noise=0.6, seed=2)
    full = base.run_family(volume_flow, df, "5m")
    trunc = base.run_family(volume_flow, df.iloc[:k], "5m")
    a = full["f_volume_flow_score"].iloc[:k].to_numpy()
    b = trunc["f_volume_flow_score"].to_numpy()
    assert np.allclose(a, b, atol=1e-9)


# ── FVG primitive ────────────────────────────────────────────────────
def test_fair_value_gap_bullish():
    highs = [10, 10, 13, 13]
    lows = [9, 9, 12, 12]
    df = syn.from_hl(highs, lows)
    fvg = smc_fallback.fair_value_gaps(df)
    assert fvg["fvg_dir"].iloc[2] == 1.0          # bull gap on 3rd candle
    assert fvg["fvg_top"].iloc[2] == 12.0 and fvg["fvg_bottom"].iloc[2] == 10.0
    assert fvg["fvg_dir"].iloc[0] == 0.0          # no gap without 2 priors


# ── smc_orderflow ────────────────────────────────────────────────────
def test_smc_bounds_and_warmup():
    out = base.run_family(smc_orderflow, syn.trend(120, 0.1, noise=0.5, seed=1), "5m")
    sc, cf = out["f_smc_orderflow_score"], out["f_smc_orderflow_conf"]
    assert sc.between(-1, 1).all() and cf.between(0, 1).all()
    assert cf.iloc[0] == 0.0                       # no swings yet -> no confidence


def test_smc_structure_bullish_on_uptrend():
    out = base.run_family(smc_orderflow, syn.trend(120, 0.25), "5m")
    assert out["f_smc_orderflow_score"].iloc[-1] > 0.0


@pytest.mark.parametrize("k", [60, 90])
def test_smc_truncation_invariant(k):
    df = syn.trend(120, 0.12, noise=1.2, seed=7)
    full = base.run_family(smc_orderflow, df, "5m")
    trunc = base.run_family(smc_orderflow, df.iloc[:k], "5m")
    a = full["f_smc_orderflow_score"].iloc[:k].to_numpy()
    b = trunc["f_smc_orderflow_score"].to_numpy()
    assert np.allclose(a, b, atol=1e-9)
