"""Position sizing + R math (jesse-style). Paper: $100 = 1R (config.R_USD).

Deterministic and pure. qty = risk_usd / per-share risk; fractional shares are fine
in the paper/shadow book. R-multiple of an open trade is signed by side.
"""
from __future__ import annotations

from .. import config


def position_size(entry: float, stop: float, r_usd: float | None = None) -> float:
    """Shares such that a stop-out loses exactly r_usd. 0 if risk is degenerate."""
    r_usd = config.R_USD if r_usd is None else r_usd
    risk = abs(entry - stop)
    if risk <= 0 or entry <= 0:
        return 0.0
    return r_usd / risk


def r_multiple(entry: float, stop: float, price: float, side: str) -> float:
    """Signed R of `price` relative to entry, in units of the initial risk."""
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    delta = (price - entry) if side == "long" else (entry - price)
    return delta / risk


def target_for_r(entry: float, stop: float, r: float, side: str) -> float:
    """Price at `r` R from entry on the given side."""
    risk = abs(entry - stop)
    return entry + r * risk if side == "long" else entry - r * risk
