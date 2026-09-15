"""No-look-ahead MTF merge — the leakage killer.

`merge_informative` shifts a higher-TF frame's index from its OPEN to its CLOSE
(`t -> t + tf`), so a bar's values become visible only from the base bar at or
after the higher bar has fully closed, then merge_asof (direction='backward')
carries each completed higher bar forward onto the base rows until the next one
closes. Because only PAST completed higher bars ever contribute, appending future
base data can never change an earlier merged row — the property the
truncation-invariance test enforces.
"""
from __future__ import annotations

import pandas as pd

from . import resample


def merge_informative(base: pd.DataFrame, higher: pd.DataFrame, tf: str,
                      prefix: str | None = None) -> pd.DataFrame:
    """Left-merge completed `higher`-TF bars onto `base` with no look-ahead.

    Higher columns are prefixed (`{tf}_open`, ...). A higher bar labeled `t`
    (open) is exposed only to base rows with timestamp >= `t + tf` (its close).
    """
    prefix = prefix or tf
    out = base.sort_index().copy()
    if higher.empty:
        for c in ("open", "high", "low", "close", "volume"):
            if c in base.columns or True:
                out[f"{prefix}_{c}"] = pd.NA
        return out
    h = higher.sort_index().copy()
    h.index = h.index + resample.tf_delta(tf)   # index := close/availability time
    h = h.add_prefix(f"{prefix}_")
    merged = pd.merge_asof(out, h, left_index=True, right_index=True,
                           direction="backward")
    merged.index.name = base.index.name
    return merged


def build_mtf_frame(base_1m: pd.DataFrame, higher_tfs) -> pd.DataFrame:
    """Base 1m frame + each higher TF (resampled from the SAME 1m then merged
    leak-free). This is the shared shape later reused by build_features()."""
    out = base_1m.sort_index().copy()
    for tf in higher_tfs:
        hi = resample.resample(base_1m, tf)
        out = merge_informative(out, hi, tf)
    return out
