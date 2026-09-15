"""Golden-slice regression — a fixed synthetic 1m slice must reproduce the exact
committed plan list. Guards the whole decision chain (families -> merge -> regime ->
scorer -> plan) against silent drift.

Synthetic (not a live SPY slice) so the fixture is reproducible: real market data
shifts every session. Regenerate deliberately with `python -m tests.test_golden`
after an intended engine change, then review the diff.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from trader.engine import pipeline, plan
from tests.fixtures import synthetic as syn

GOLDEN = Path(__file__).parent / "golden" / "plans_synth.json"
FIELDS = ("side", "created_at", "entry", "stop", "risk_per_share", "qty",
          "tp1", "tp2", "tp3", "combined", "regime")


def _build_slice():
    n = 800
    t = np.arange(n)
    close = 100 + 0.06 * t + 2.5 * np.sin(t / 25.0) + np.random.RandomState(21).randn(n) * 0.3
    return syn.ohlc_from_close(close, spread=0.15, start="2026-06-01 09:30", freq="1min")


def compute_plans() -> list[dict]:
    feat = pipeline.features_for_tf(_build_slice(), "5m", symbol="SYN")
    plans = plan.plans_from_features(feat, "SYN", "5m")
    return [{k: p[k] for k in FIELDS} for p in plans]


def test_golden_plans_reproduce():
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert compute_plans() == expected


if __name__ == "__main__":   # regenerate the golden deliberately
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(compute_plans(), indent=2), encoding="utf-8")
    print(f"wrote {GOLDEN}")
