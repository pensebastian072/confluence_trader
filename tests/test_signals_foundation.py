"""P3 foundation tests — family contract, swing engine, momentum. Network-free."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trader.signals import base, momentum, swings
from tests.fixtures import synthetic as syn


# ── contract / totality ──────────────────────────────────────────────
class _Boom:
    NAME = "boom"

    @staticmethod
    def populate(df, tf):
        raise RuntimeError("kaboom")


class _Empty:
    NAME = "empty"

    @staticmethod
    def populate(df, tf):
        return df.copy()  # forgets to add columns


def test_run_family_totality():
    df = syn.trend(30, 0.1)
    for fam in (_Boom, _Empty):
        out = base.run_family(fam, df, "5m")
        assert (out[base.score_col(fam.NAME)] == 0.0).all()
        assert (out[base.conf_col(fam.NAME)] == 0.0).all()


def test_finalize_clamps_and_fills():
    df = syn.trend(5, 0.0)
    out = base.finalize(df.copy(), "x", pd.Series([2, -2, np.nan, 0.5, 0.0], index=df.index),
                        pd.Series([9, -1, 0.5, np.nan, 0.2], index=df.index))
    assert list(out["f_x_score"]) == [1.0, -1.0, 0.0, 0.5, 0.0]
    assert list(out["f_x_conf"]) == [1.0, 0.0, 0.5, 0.0, 0.2]


# ── swings ───────────────────────────────────────────────────────────
def test_swing_high_detected_and_confirmed_late():
    # single clear peak at index 5; left=right=2 -> confirmed at index 7.
    highs = [10, 11, 12, 13, 14, 20, 14, 13, 12, 11, 10]
    lows = [h - 1 for h in highs]
    df = syn.from_hl(highs, lows)
    s = swings.compute(df, left=2, right=2)
    assert bool(s["swing_high_new"].iloc[7]) is True
    assert s["swing_high_price"].iloc[7] == 20.0
    assert not s["swing_high_new"].iloc[5]        # NOT emitted at the peak itself
    assert s["swing_high"].iloc[8] == 20.0        # carried forward


@pytest.mark.parametrize("k", [8, 12, 20])
def test_swings_truncation_invariant(k):
    df = syn.trend(40, 0.0, noise=1.5, seed=3)
    full = swings.compute(df, left=2, right=2)
    trunc = swings.compute(df.iloc[:k], left=2, right=2)
    cols = ["swing_high_price", "swing_low_price"]
    a = full.loc[trunc.index, cols].fillna(-999)
    b = trunc[cols].fillna(-999)
    assert (a.values == b.values).all()           # bit-identical on overlap


# ── momentum ─────────────────────────────────────────────────────────
def test_momentum_sign_tracks_trend():
    up = base.run_family(momentum, syn.trend(120, 0.15), "5m")
    dn = base.run_family(momentum, syn.trend(120, -0.15), "5m")
    assert up["f_momentum_score"].iloc[-1] > 0.3
    assert dn["f_momentum_score"].iloc[-1] < -0.3


def test_momentum_bounds_and_warmup_neutral():
    out = base.run_family(momentum, syn.trend(120, 0.1, noise=0.5, seed=1), "5m")
    sc, cf = out["f_momentum_score"], out["f_momentum_conf"]
    assert sc.between(-1, 1).all() and cf.between(0, 1).all()
    assert sc.iloc[0] == 0.0 and cf.iloc[0] == 0.0   # warmup -> neutral


@pytest.mark.parametrize("k", [70, 90, 110])
def test_momentum_truncation_invariant(k):
    df = syn.trend(120, 0.12, noise=0.6, seed=2)
    full = base.run_family(momentum, df, "5m")
    trunc = base.run_family(momentum, df.iloc[:k], "5m")
    a = full["f_momentum_score"].iloc[:k].to_numpy()
    b = trunc["f_momentum_score"].to_numpy()
    assert np.allclose(a, b, atol=1e-9)              # causal indicators: no leak
