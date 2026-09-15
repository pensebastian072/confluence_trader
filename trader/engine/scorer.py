"""Confluence scorer — combines the six families into one decision.

    combined = Σ w·score·conf / Σ w·conf   (families with conf 0 drop out)

Weights are the regime-keyed presets (config.REGIME_WEIGHTS), applied per bar from
the regime series. A side emits only when ALL gates pass:
  - |combined| >= EMIT_MIN_COMBINED
  - >= MIN_FAMILIES_AGREE families agree on the sign (with conf > 0)
  - higher-TF bias not opposing (bias_up_ok / bias_dn_ok)
Pure and vectorised; the scan takes the last row, the backtest the whole frame.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config
from ..signals import base

FAMILIES = config.SIGNAL_FAMILIES


def _weights_frame(regime: pd.Series) -> pd.DataFrame:
    """Per-bar family weights from the regime label."""
    default = config.REGIME_WEIGHTS[config.DEFAULT_REGIME]
    data = {}
    for fam in FAMILIES:
        data[fam] = regime.map(lambda r: config.REGIME_WEIGHTS.get(r, default)[fam])
    return pd.DataFrame(data, index=regime.index)


def combined_score(df: pd.DataFrame, regime: pd.Series) -> pd.Series:
    w = _weights_frame(regime)
    num = pd.Series(0.0, index=df.index)
    den = pd.Series(0.0, index=df.index)
    for fam in FAMILIES:
        sc = df.get(base.score_col(fam))
        cf = df.get(base.conf_col(fam))
        if sc is None or cf is None:
            continue
        num = num + w[fam] * sc * cf
        den = den + w[fam] * cf
    return (num / den.where(den > 0)).fillna(0.0)


def _agree_counts(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    longs = pd.Series(0, index=df.index)
    shorts = pd.Series(0, index=df.index)
    for fam in FAMILIES:
        sc = df.get(base.score_col(fam))
        cf = df.get(base.conf_col(fam))
        if sc is None or cf is None:
            continue
        active = cf > 0
        longs = longs + ((sc > 0) & active).astype(int)
        shorts = shorts + ((sc < 0) & active).astype(int)
    return longs, shorts


def evaluate(df: pd.DataFrame, regime: pd.Series,
             bias_up_ok=None, bias_dn_ok=None) -> pd.DataFrame:
    """Attach combined / n_agree / emit_long / emit_short columns."""
    out = df.copy()
    combined = combined_score(out, regime)
    n_long, n_short = _agree_counts(out)
    if bias_up_ok is None:
        bias_up_ok = pd.Series(True, index=out.index)
    if bias_dn_ok is None:
        bias_dn_ok = pd.Series(True, index=out.index)

    out["regime"] = regime.values
    out["combined"] = combined
    out["n_agree_long"] = n_long
    out["n_agree_short"] = n_short
    out["emit_long"] = ((combined >= config.EMIT_MIN_COMBINED)
                        & (n_long >= config.MIN_FAMILIES_AGREE)
                        & bias_up_ok.astype(bool).values)
    out["emit_short"] = ((combined <= -config.EMIT_MIN_COMBINED)
                         & (n_short >= config.MIN_FAMILIES_AGREE)
                         & bias_dn_ok.astype(bool).values)
    return out


def breakdown(row: pd.Series) -> dict:
    """Per-family score/conf for a single emitted bar (explainability)."""
    return {fam: {"score": float(row.get(base.score_col(fam), 0.0)),
                  "conf": float(row.get(base.conf_col(fam), 0.0))}
            for fam in FAMILIES}
