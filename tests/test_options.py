"""P4 options tests — gex core, CBOE parse, options_levels family."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from trader import config
from trader.data import options_snapshot
from trader.signals import base, options_levels
from trader.vendor import gex
from tests.fixtures import synthetic as syn


# ── gex core ─────────────────────────────────────────────────────────
def test_bs_gamma_peaks_atm_and_guards():
    atm = gex.bs_gamma(100, 100, 0.1, 0.2)
    otm = gex.bs_gamma(100, 130, 0.1, 0.2)
    assert atm > otm > 0
    assert gex.bs_gamma(0, 100, 0.1, 0.2) == 0.0       # degenerate -> 0
    assert gex.bs_gamma(100, 100, 0.0, 0.2) == 0.0


def test_total_gex_sign_by_side():
    call = [{"strike": 100, "iv": 0.2, "t_years": 0.1, "call_oi": 1000, "put_oi": 0}]
    put = [{"strike": 100, "iv": 0.2, "t_years": 0.1, "call_oi": 0, "put_oi": 1000}]
    assert gex.total_gex(100, call) > 0
    assert gex.total_gex(100, put) < 0


def test_zero_gamma_crossing():
    chain = [{"strike": 90, "iv": 0.2, "t_years": 0.1, "call_oi": 0, "put_oi": 1000},
             {"strike": 110, "iv": 0.2, "t_years": 0.1, "call_oi": 1000, "put_oi": 0}]
    zg = gex.zero_gamma(chain, 80, 120)
    assert zg is not None and 90 < zg < 110


def test_max_pain_and_walls():
    chain = [{"strike": k, "iv": 0.2, "t_years": 0.05,
              "call_oi": 100, "put_oi": 100} for k in range(90, 111, 5)]
    chain[2]["call_oi"] = 5000   # strike 100 heavy
    mp = gex.max_pain(chain)
    assert 95 <= mp <= 105
    walls = gex.oi_walls(chain, n=1)
    assert walls["call_walls"] == [100.0]


# ── CBOE parse ───────────────────────────────────────────────────────
def test_parse_chain_aggregates_and_skips_bad():
    raw = {"data": {"current_price": 100.0, "options": [
        {"option": "XYZ260718C00100000", "open_interest": 500, "iv": 0.2},
        {"option": "XYZ260718P00100000", "open_interest": 300, "iv": 0.25},
        {"option": "GARBAGE", "open_interest": 999, "iv": 0.2},
    ]}}
    now = datetime(2026, 7, 8, tzinfo=timezone.utc)
    parsed = options_snapshot.parse_chain(raw, now)
    assert parsed["spot"] == 100.0
    assert parsed["front_expiry"] == "2026-07-18"
    row = [r for r in parsed["gex_chain"] if r["strike"] == 100.0][0]
    assert row["call_oi"] == 500 and row["put_oi"] == 300   # garbage row skipped


# ── options_levels family ────────────────────────────────────────────
def _snapshot(spot=100.0, max_pain_strike=100.0):
    chain = [{"strike": float(k), "iv": 0.2, "t_years": 0.05,
              "call_oi": 100.0, "put_oi": 100.0} for k in range(90, 111, 2)]
    return {"spot": spot, "snapshot_date": "2026-07-08", "front_expiry": "2026-07-18",
            "gex_chain": chain, "pain_chain": chain}


def _df(price, n=30):
    return syn.ohlc_from_close(np.full(n, price))


def test_options_levels_neutral_without_snapshot():
    out = base.run_family(options_levels, _df(105), "5m")
    assert (out["f_options_levels_score"] == 0.0).all()
    assert (out["f_options_levels_conf"] == 0.0).all()


def test_options_levels_stale_is_neutral():
    df = _df(105)
    df.attrs["options_snapshot"] = _snapshot()
    df.attrs["options_age_days"] = config.OPTIONS_STALE_DAYS + 1
    out = base.run_family(options_levels, df, "5m")
    assert (out["f_options_levels_conf"] == 0.0).all()


def test_options_levels_pulls_toward_max_pain():
    above = _df(106)
    above.attrs.update(options_snapshot=_snapshot(), options_age_days=0)
    below = _df(94)
    below.attrs.update(options_snapshot=_snapshot(), options_age_days=0)
    o_above = options_levels.populate(above, "5m")
    o_below = options_levels.populate(below, "5m")
    assert o_above["f_options_levels_score"].iloc[-1] < 0    # above pain -> short pull
    assert o_below["f_options_levels_score"].iloc[-1] > 0    # below pain -> long pull
    assert (o_above["f_options_levels_conf"] > 0).all()      # fresh -> confident


def test_options_levels_conf_decays_with_age():
    d0, d2 = _df(106), _df(106)
    d0.attrs.update(options_snapshot=_snapshot(), options_age_days=0)
    d2.attrs.update(options_snapshot=_snapshot(), options_age_days=2)
    c0 = options_levels.populate(d0, "5m")["f_options_levels_conf"].iloc[-1]
    c2 = options_levels.populate(d2, "5m")["f_options_levels_conf"].iloc[-1]
    assert 0 < c2 < c0


# ── live CBOE (network) ──────────────────────────────────────────────
@pytest.mark.network
def test_live_cboe_spy():
    raw, err = options_snapshot.fetch_raw("SPY")
    assert err is None and raw is not None
    parsed = options_snapshot.parse_chain(raw)
    assert parsed["spot"] > 0 and len(parsed["gex_chain"]) > 0
    assert gex.max_pain(parsed["pain_chain"]) is not None
