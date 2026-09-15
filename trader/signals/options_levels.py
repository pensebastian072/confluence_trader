"""Options-levels family — GEX / zero-gamma flip / max pain / OI walls from the
daily CBOE snapshot, ffilled onto intraday. Confidence decays with snapshot age
and drops to 0 past OPTIONS_STALE_DAYS (fail-safe, off the hot path).

Direction: price is pulled toward max pain into expiry (above pain -> mild short,
below -> mild long). The gamma regime (net GEX sign, zero-gamma flip) is attached
as context and modestly scales confidence rather than flipping direction.

The snapshot is read off-path: from df.attrs['options_snapshot'] if the pipeline
injected it, else loaded from the latest cache for df.attrs['symbol']. No symbol /
no snapshot / stale -> neutral (0, 0).
"""
from __future__ import annotations

import numpy as np

from .. import config
from ..data import options_snapshot
from ..vendor import gex
from . import base

NAME = "options_levels"

PAIN_SCALE = 0.01     # price distance to max pain normalised by price * this
BASE_CONF = 0.7


def _get_snapshot(df):
    snap = df.attrs.get("options_snapshot")
    if snap is not None:
        return snap, df.attrs.get("options_age_days", 0)
    sym = df.attrs.get("symbol")
    if not sym:
        return None, None
    parsed, age, _err = options_snapshot.load_latest(sym)
    return parsed, age


def populate(df, tf):
    out = df.copy()
    snap, age = _get_snapshot(df)
    if snap is None or age is None or age > config.OPTIONS_STALE_DAYS:
        return base.neutral(out, NAME)

    spot = float(snap.get("spot") or 0.0)
    gex_chain = snap.get("gex_chain") or []
    pain_chain = snap.get("pain_chain") or []
    if spot <= 0 or not gex_chain:
        return base.neutral(out, NAME)

    zg = gex.zero_gamma(gex_chain, spot * 0.9, spot * 1.1)
    mp = gex.max_pain(pain_chain)
    net_gex = gex.total_gex(spot, gex_chain)
    walls = gex.oi_walls(gex_chain)

    close = out["close"]
    pain_s = np.tanh((mp - close) / (close * PAIN_SCALE)) if mp else 0.0
    score = 0.6 * pain_s

    age_factor = max(0.0, 1.0 - age / config.OPTIONS_STALE_DAYS)
    conf = BASE_CONF * age_factor

    # attach daily levels (constant across the intraday session).
    out["opt_zero_gamma"] = zg
    out["opt_max_pain"] = mp
    out["opt_net_gex"] = net_gex
    out["opt_call_wall"] = walls["call_walls"][0] if walls["call_walls"] else np.nan
    out["opt_put_wall"] = walls["put_walls"][0] if walls["put_walls"] else np.nan
    return base.finalize(out, NAME, score, conf)
