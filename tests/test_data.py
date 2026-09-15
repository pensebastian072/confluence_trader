"""P1 data-layer tests. Cache/merge logic is network-free; a single live fetch is
marked `network` (deselected by default)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from trader import config
from trader.data import alpaca_client, bar_store, universe


def _synth(n: int, start: str = "2026-01-05 14:30", freq: str = "1min") -> pd.DataFrame:
    idx = pd.date_range(start=start, periods=n, freq=freq, tz="UTC", name="timestamp")
    base = range(n)
    return pd.DataFrame({
        "open": [100 + i for i in base], "high": [101 + i for i in base],
        "low": [99 + i for i in base], "close": [100.5 + i for i in base],
        "volume": [1000 + i for i in base],
    }, index=idx)


# ── bar_store ────────────────────────────────────────────────────────
def test_merge_upsert_add_then_idempotent(sandbox):
    df = _synth(10)
    s1 = bar_store.merge_upsert("SPY", "1m", df)
    assert s1 == {"added": 10, "updated": 0, "total": 10}
    # second identical merge: no new rows, all "updated", file unchanged.
    s2 = bar_store.merge_upsert("SPY", "1m", df)
    assert s2["added"] == 0 and s2["updated"] == 10 and s2["total"] == 10
    assert len(bar_store.load("SPY", "1m")) == 10


def test_merge_upsert_extends_and_overwrites(sandbox):
    bar_store.merge_upsert("QQQ", "5m", _synth(5, freq="5min"))
    # overlapping 3 + 4 new, with a changed close on the overlap.
    ext = _synth(7, freq="5min")
    ext.loc[ext.index[0], "close"] = 999.0
    s = bar_store.merge_upsert("QQQ", "5m", ext)
    assert s["added"] == 2 and s["updated"] == 5 and s["total"] == 7
    got = bar_store.load("QQQ", "5m")
    assert got.iloc[0]["close"] == 999.0  # newest wins
    assert got.index.is_monotonic_increasing


def test_load_empty_and_coverage(sandbox):
    assert bar_store.load("NONE", "1m").empty
    assert bar_store.last_timestamp("NONE", "1m") is None
    assert bar_store.coverage("NONE", "1m")["rows"] == 0
    bar_store.merge_upsert("SPY", "1h", _synth(3, freq="1h"))
    cov = bar_store.coverage("SPY", "1h")
    assert cov["rows"] == 3 and cov["start"] and cov["end"]


# ── alpaca_client ────────────────────────────────────────────────────
def test_timeframe_mapping_and_unsupported():
    for tf in ("1m", "5m", "15m", "1h", "4h"):
        assert alpaca_client._timeframe(tf) is not None
    with pytest.raises(ValueError):
        alpaca_client._timeframe("3d")


def test_get_bars_no_creds_degrades(monkeypatch):
    monkeypatch.setattr(config, "alpaca_creds", lambda: (None, None, config.ALPACA_PAPER_BASE, True))
    df, err = alpaca_client.get_bars("SPY", "1m", datetime(2026, 1, 5, tzinfo=timezone.utc))
    assert df.empty and err and "creds not configured" in err


# ── universe ─────────────────────────────────────────────────────────
def test_backfill_windows():
    now = datetime(2026, 7, 8, tzinfo=timezone.utc)
    assert (now - universe.backfill_start("1m", now)) == timedelta(days=90)
    assert (now - universe.backfill_start("4h", now)) == timedelta(days=3650)


# ── live (network) ───────────────────────────────────────────────────
@pytest.mark.network
def test_live_fetch_spy_1m():
    start = datetime.now(timezone.utc) - timedelta(days=3)
    end = datetime.now(timezone.utc) - timedelta(minutes=16)
    df, err = alpaca_client.get_bars("SPY", "1m", start, end)
    assert err is None
    assert not df.empty
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.is_monotonic_increasing and df.index.tz is not None
