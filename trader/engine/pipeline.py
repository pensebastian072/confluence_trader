"""THE single features path — used identically by the live scan (last row) and the
backtest (full history). Resample 1m -> setup TF, run all six families, classify
regime, merge leak-free higher-TF (1h/4h) momentum bias, then score + gate. P8's
backtest/features.py calls this so live and backtest decisions cannot drift.
"""
from __future__ import annotations

import pandas as pd

from .. import config
from ..mtf import merge, resample
from ..signals import (base, fibonacci, momentum, options_levels, patterns,
                       smc_orderflow, volume_flow, wilder)
from . import regime as regime_mod
from . import scorer

ATR_LEN = 14

# Order matters only for column accumulation, not results (families are independent).
FAMILY_MODULES = (momentum, volume_flow, smc_orderflow, patterns, fibonacci, options_levels)

BIAS_OPPOSE = 0.2   # higher-TF momentum beyond this magnitude opposes the setup


def _setup_frame(df_1m: pd.DataFrame, setup_tf: str) -> pd.DataFrame:
    return df_1m.copy() if setup_tf == "1m" else resample.resample(df_1m, setup_tf)


def _bias_ok(df_1m: pd.DataFrame, setup_frame: pd.DataFrame):
    """Leak-safe 1h/4h momentum bias merged onto the setup frame. Returns
    (bias_up_ok, bias_dn_ok) boolean Series. Warmup (NaN) counts as non-opposing."""
    up = pd.Series(True, index=setup_frame.index)
    dn = pd.Series(True, index=setup_frame.index)
    for htf in config.BIAS_TFS:
        h = resample.resample(df_1m, htf)
        hm = base.run_family(momentum, h, htf)[base.score_col("momentum")]
        higher = pd.DataFrame({"m": hm})
        merged = merge.merge_informative(setup_frame, higher, htf, prefix=htf)
        col = merged[f"{htf}_m"].reindex(setup_frame.index).fillna(0.0)
        up &= col > -BIAS_OPPOSE
        dn &= col < BIAS_OPPOSE
    return up, dn


def features_for_tf(df_1m: pd.DataFrame, setup_tf: str, symbol: str | None = None,
                    options_snapshot: dict | None = None,
                    options_age_days: int | None = None) -> pd.DataFrame:
    """Full feature + decision frame for one setup timeframe."""
    feat = _setup_frame(df_1m, setup_tf)
    feat.attrs["symbol"] = symbol
    if options_snapshot is not None:
        feat.attrs["options_snapshot"] = options_snapshot
        feat.attrs["options_age_days"] = options_age_days or 0

    for mod in FAMILY_MODULES:
        feat.attrs["symbol"] = symbol
        if options_snapshot is not None:
            feat.attrs["options_snapshot"] = options_snapshot
            feat.attrs["options_age_days"] = options_age_days or 0
        feat = base.run_family(mod, feat, setup_tf)

    reg = regime_mod.classify(feat)
    up, dn = _bias_ok(df_1m, feat)
    scored = scorer.evaluate(feat, reg, up, dn)
    scored["atr"] = wilder.atr(scored["high"], scored["low"], scored["close"], ATR_LEN)
    return scored
