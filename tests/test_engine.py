"""P5 engine tests — sizing, scorer, plan, exits, pipeline. Network-free."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from trader import config
from trader.engine import exits, pipeline, plan, scorer, sizing
from trader.signals import base
from tests.fixtures import synthetic as syn

NOW = datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)


# ── sizing ───────────────────────────────────────────────────────────
def test_position_size_and_r_math():
    assert sizing.position_size(100, 98) == config.R_USD / 2.0
    assert sizing.position_size(100, 100) == 0.0          # degenerate
    assert sizing.r_multiple(100, 98, 102, "long") == 1.0
    assert sizing.r_multiple(100, 98, 96, "long") == -2.0
    assert sizing.r_multiple(100, 102, 98, "short") == 1.0
    assert sizing.target_for_r(100, 98, 2, "long") == 104.0


# ── scorer ───────────────────────────────────────────────────────────
def _frame(rows: dict, n: int = 3) -> pd.DataFrame:
    idx = pd.date_range("2026-01-05", periods=n, freq="5min", tz="UTC")
    df = pd.DataFrame(index=idx)
    for fam in config.SIGNAL_FAMILIES:
        sc, cf = rows.get(fam, (0.0, 0.0))
        df[base.score_col(fam)] = sc
        df[base.conf_col(fam)] = cf
    return df


def test_combined_score_weighted_mean():
    df = _frame({"momentum": (0.8, 1.0)})           # only momentum active
    reg = pd.Series(["transitional"] * len(df), index=df.index)
    assert np.allclose(scorer.combined_score(df, reg), 0.8)


def test_emit_requires_agreement_and_threshold():
    reg = pd.Series(["transitional"] * 3)
    # one strong family: combined high but only 1 agrees -> no emit
    df1 = _frame({"momentum": (0.9, 1.0)})
    ev1 = scorer.evaluate(df1, pd.Series(reg.values, index=df1.index))
    assert not ev1["emit_long"].any()
    # three families agree at 0.7 -> emit
    df2 = _frame({"momentum": (0.7, 1.0), "volume_flow": (0.7, 1.0), "fibonacci": (0.7, 1.0)})
    ev2 = scorer.evaluate(df2, pd.Series(reg.values, index=df2.index))
    assert ev2["emit_long"].all() and not ev2["emit_short"].any()


def test_bias_veto_blocks_emit():
    reg = pd.Series(["transitional"] * 3)
    df = _frame({"momentum": (0.7, 1.0), "volume_flow": (0.7, 1.0), "fibonacci": (0.7, 1.0)})
    opposing = pd.Series([False] * 3, index=df.index)
    ev = scorer.evaluate(df, pd.Series(reg.values, index=df.index), bias_up_ok=opposing)
    assert not ev["emit_long"].any()                 # higher-TF bias vetoes


# ── plan ─────────────────────────────────────────────────────────────
def test_build_plan_long_geometry():
    p = plan.build_plan(symbol="SPY", setup_tf="5m", side="long", close=100.0, atr=1.0,
                        swing_high=101.0, swing_low=98.0, combined=0.7, regime="trend",
                        breakdown={}, now=NOW)
    assert p.entry == 100.0
    assert p.stop == 98.0 - config.STOP_ATR_BUFFER * 1.0     # 97.75
    assert p.risk_per_share == pytest.approx(2.25)
    assert p.qty == pytest.approx(config.R_USD / 2.25, rel=1e-4)
    assert p.tp1 == pytest.approx(100.0 + 2.25)             # +1R, unsnapped
    assert p.tp3 == pytest.approx(100.0 + 4 * 2.25)


def test_build_plan_snaps_to_level():
    p = plan.build_plan(symbol="SPY", setup_tf="5m", side="long", close=100.0, atr=1.0,
                        swing_high=101.0, swing_low=98.0, combined=0.7, regime="trend",
                        breakdown={}, snap_levels=[102.3], now=NOW)  # near +1R 102.25
    assert p.tp1 == 102.3 and p.levels_used.get("tp1") == 102.3


def test_build_plan_invalid_geometry_none():
    assert plan.build_plan(symbol="SPY", setup_tf="5m", side="long", close=100.0, atr=1.0,
                           swing_high=101.0, swing_low=101.0, combined=0.7, regime="trend",
                           breakdown={}, now=NOW) is None      # stop above entry


# ── exits ────────────────────────────────────────────────────────────
def _long_pos():
    p = plan.build_plan(symbol="SPY", setup_tf="5m", side="long", close=100.0, atr=1.0,
                        swing_high=101.0, swing_low=98.0, combined=0.7, regime="trend",
                        breakdown={}, now=NOW)
    return exits.open_position(p)


def test_exit_tp1_moves_to_breakeven_then_stop():
    pos = _long_pos()
    pos, ev = exits.process_bar(pos, {"high": 103.0, "low": 100.0, "close": 102.5})
    assert ev[0]["type"] == "TP1" and pos["stop"] == pos["entry"]
    assert pos["remaining_frac"] == pytest.approx(0.6)
    pos, ev = exits.process_bar(pos, {"high": 100.5, "low": 99.0, "close": 99.5})
    assert ev[0]["type"] == "STOP" and pos["closed"]         # BE stop hit


def test_exit_same_bar_stop_and_target_stop_wins():
    pos = _long_pos()
    # bar spans both the stop and tp3 -> STOP first (conservative)
    pos, ev = exits.process_bar(pos, {"high": 120.0, "low": 90.0, "close": 100.0})
    assert [e["type"] for e in ev] == ["STOP"] and pos["closed"]


def test_exit_eod_and_choch():
    pos = _long_pos()
    pos, ev = exits.process_bar(pos, {"high": 100.5, "low": 99.9, "close": 100.2, "is_eod": True})
    assert ev[-1]["type"] == "EOD" and pos["closed"]
    pos2 = _long_pos()
    pos2, ev2 = exits.process_bar(pos2, {"high": 100.5, "low": 99.9, "close": 100.1, "choch_against": True})
    assert ev2[-1]["type"] == "CHOCH"


# ── pipeline ─────────────────────────────────────────────────────────
def test_pipeline_deterministic_and_columns():
    df = syn.trend(600, 0.05, noise=1.0, seed=11, freq="1min")
    a = pipeline.features_for_tf(df, "5m", symbol="TEST")
    b = pipeline.features_for_tf(df, "5m", symbol="TEST")
    assert np.allclose(a["combined"], b["combined"])
    for col in ("combined", "regime", "emit_long", "emit_short", "n_agree_long"):
        assert col in a.columns


@pytest.mark.parametrize("k", [200, 400])
def test_pipeline_truncation_invariant(k):
    df = syn.trend(600, 0.05, noise=1.0, seed=12, freq="1min")
    full = pipeline.features_for_tf(df, "5m", symbol="TEST")
    trunc = pipeline.features_for_tf(df.iloc[:k], "5m", symbol="TEST")
    a = full["combined"].reindex(trunc.index).to_numpy()
    b = trunc["combined"].to_numpy()
    assert np.allclose(a, b, atol=1e-9)
