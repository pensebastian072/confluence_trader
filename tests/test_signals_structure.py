"""P4 structure-family tests — fibonacci + patterns. Network-free."""
from __future__ import annotations

import numpy as np
import pytest

from trader.signals import base, fibonacci, patterns
from tests.fixtures import synthetic as syn


# ── fibonacci ────────────────────────────────────────────────────────
def test_fib_bounds_and_warmup():
    out = base.run_family(fibonacci, syn.trend(120, 0.1, noise=0.8, seed=4), "5m")
    sc, cf = out["f_fibonacci_score"], out["f_fibonacci_conf"]
    assert sc.between(-1, 1).all() and cf.between(0, 1).all()
    assert sc.iloc[0] == 0.0 and cf.iloc[0] == 0.0


def test_fib_levels_within_leg():
    out = fibonacci.populate(syn.trend(120, 0.0, noise=2.0, seed=9), "5m")
    m = out.dropna(subset=["swing_high", "swing_low"])
    m = m[m["swing_high"] > m["swing_low"]]
    # .5 retrace must sit between the leg low and high.
    assert (m["fib_500"] <= m["swing_high"] + 1e-9).all()
    assert (m["fib_500"] >= m["swing_low"] - 1e-9).all()


@pytest.mark.parametrize("k", [60, 90])
def test_fib_truncation_invariant(k):
    df = syn.trend(120, 0.05, noise=1.5, seed=6)
    full = base.run_family(fibonacci, df, "5m")
    trunc = base.run_family(fibonacci, df.iloc[:k], "5m")
    a = full["f_fibonacci_score"].iloc[:k].to_numpy()
    b = trunc["f_fibonacci_score"].to_numpy()
    assert np.allclose(a, b, atol=1e-9)


# ── patterns ─────────────────────────────────────────────────────────
def _dbl_bottom():
    p = [20, 19, 18, 17, 16, 15, 16, 17, 18, 17, 16, 15.05, 16, 17, 18.5, 18.6]
    return syn.from_hl([x + 0.1 for x in p], [x - 0.1 for x in p])


def _dbl_top():
    p = [10, 11, 12, 13, 14, 15, 14, 13, 12, 13, 14, 14.95, 14, 13, 11.5, 11.4]
    return syn.from_hl([x + 0.1 for x in p], [x - 0.1 for x in p])


def test_double_bottom_completes_bullish():
    out = patterns.populate(_dbl_bottom(), "5m")
    assert (out["f_patterns_score"] == 1.0).any()      # bullish completion fired


def test_double_top_completes_bearish():
    out = patterns.populate(_dbl_top(), "5m")
    assert (out["f_patterns_score"] == -1.0).any()     # bearish completion fired


def test_patterns_bounds_and_warmup():
    out = base.run_family(patterns, syn.trend(120, 0.1, noise=0.8, seed=4), "5m")
    sc, cf = out["f_patterns_score"], out["f_patterns_conf"]
    assert sc.between(-1, 1).all() and cf.between(0, 1).all()
    assert sc.iloc[0] == 0.0 and cf.iloc[0] == 0.0


@pytest.mark.parametrize("k", [10, 14])
def test_patterns_truncation_invariant(k):
    df = _dbl_bottom()
    full = patterns.populate(df, "5m")
    trunc = patterns.populate(df.iloc[:k], "5m")
    a = full["f_patterns_score"].iloc[:k].to_numpy()
    b = trunc["f_patterns_score"].to_numpy()
    assert np.allclose(a, b, atol=1e-9)
