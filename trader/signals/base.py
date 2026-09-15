"""Signal-family contract. Every family exposes `NAME` and
`populate(df, tf) -> df`, adding two columns:

    f_{NAME}_score  in [-1, +1]   (directional: + long, - short)
    f_{NAME}_conf   in [0, 1]     (confidence / reliability)

plus optional tag/level columns. Families must be vectorized and total: any
failure resolves to the neutral (0, 0) contribution, never an exception on the
scan path. `run_family` enforces that guarantee.
"""
from __future__ import annotations

import pandas as pd


def score_col(name: str) -> str:
    return f"f_{name}_score"


def conf_col(name: str) -> str:
    return f"f_{name}_conf"


def finalize(df: pd.DataFrame, name: str, score, conf) -> pd.DataFrame:
    """Attach clamped score/conf. Non-numeric / NaN -> 0 (neutral warmup)."""
    df[score_col(name)] = pd.to_numeric(pd.Series(score, index=df.index),
                                        errors="coerce").fillna(0.0).clip(-1.0, 1.0)
    df[conf_col(name)] = pd.to_numeric(pd.Series(conf, index=df.index),
                                       errors="coerce").fillna(0.0).clip(0.0, 1.0)
    return df


def neutral(df: pd.DataFrame, name: str) -> pd.DataFrame:
    df[score_col(name)] = 0.0
    df[conf_col(name)] = 0.0
    return df


def run_family(family, df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Run `family.populate(df, tf)` with the totality guarantee: on any
    exception or missing output columns, fall back to neutral (0, 0)."""
    name = getattr(family, "NAME", getattr(family, "__name__", "unknown"))
    try:
        out = family.populate(df, tf)
        if out is None:
            return neutral(df.copy(), name)
        if score_col(name) not in out.columns or conf_col(name) not in out.columns:
            return neutral(out, name)
        # re-clamp defensively in case a family wrote raw values.
        return finalize(out, name, out[score_col(name)], out[conf_col(name)])
    except Exception:  # noqa: BLE001 — totality: never crash the scan
        return neutral(df.copy(), name)
