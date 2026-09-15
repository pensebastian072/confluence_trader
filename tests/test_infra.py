"""P0 infra-port tests: config, journal, failsafe, clock, certs. No network."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trader import config
from trader.infra import certs, clock, failsafe, journal


# ── config ───────────────────────────────────────────────────────────
def test_regime_weights_cover_all_families():
    for regime, weights in config.REGIME_WEIGHTS.items():
        assert set(weights) == set(config.SIGNAL_FAMILIES), regime


def test_tp_fractions_sum_to_one_and_align():
    assert abs(sum(config.TP_FRACTIONS) - 1.0) < 1e-9
    assert len(config.TP_FRACTIONS) == len(config.TP_MULTIPLES)


def test_alpaca_creds_forced_paper(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "PKTEST")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "sec")
    monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets/v2")  # live!
    key, secret, base, paper = config.alpaca_creds()
    assert key == "PKTEST" and secret == "sec"
    assert paper is True and "paper-api" in base  # live endpoint refused


def test_load_watchlist_fallback(sandbox):
    assert config.load_watchlist() == ["SPY", "QQQ"]  # file absent -> fallback
    config.WATCHLIST_PATH.write_text('{"symbols": ["AAPL", "msft"]}', encoding="utf-8")
    assert config.load_watchlist() == ["AAPL", "MSFT"]


# ── journal ──────────────────────────────────────────────────────────
def test_jsonl_roundtrip_and_corrupt_skip(sandbox):
    p = config.PLANS_DIR / "x.jsonl"
    journal.append_jsonl(p, {"a": 1})
    journal.append_jsonl(p, {"a": 2})
    p.open("a", encoding="utf-8").write("{not json\n")
    recs = journal.read_jsonl(p)
    assert [r["a"] for r in recs] == [1, 2]  # corrupt line skipped


def test_state_atomic_roundtrip(sandbox):
    p = config.POSITIONS_STATE_PATH
    journal.write_state(p, {"open": 3})
    got = journal.read_state(p)
    assert got["open"] == 3 and "as_of" in got
    assert journal.read_state(config.JOURNAL_DIR / "missing.json", {"d": 1}) == {"d": 1}


# ── failsafe ─────────────────────────────────────────────────────────
def test_read_flag_missing_is_not_fresh(sandbox):
    data, fresh, err = failsafe.read_flag(config.JOURNAL_DIR / "nope.json")
    assert data is None and fresh is False and err == "missing"


def test_read_flag_stale_returns_not_fresh(sandbox):
    p = config.JOURNAL_DIR / "regime.json"
    old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    p.write_text(f'{{"generated_at": "{old}", "regime": "trend"}}', encoding="utf-8")
    data, fresh, err = failsafe.read_flag(p, max_age_s=3600)
    assert fresh is False and err == "stale" and data["regime"] == "trend"


def test_read_flag_fresh(sandbox):
    p = config.JOURNAL_DIR / "regime.json"
    now = datetime.now(timezone.utc).isoformat()
    p.write_text(f'{{"generated_at": "{now}", "regime": "chop"}}', encoding="utf-8")
    _, fresh, err = failsafe.read_flag(p, max_age_s=3600)
    assert fresh is True and err is None


def test_safe_wraps_exceptions():
    assert failsafe.safe(lambda: 1 / 0, default=-1) == (-1, "ZeroDivisionError: division by zero")
    assert failsafe.safe(lambda: 42) == (42, None)


# ── clock ────────────────────────────────────────────────────────────
def test_market_open_closed():
    # 2026-07-06 is a Monday. 14:00 UTC = 10:00 ET (open); 21:00 UTC = 17:00 ET (closed).
    assert clock.is_market_open(datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)) is True
    assert clock.is_market_open(datetime(2026, 7, 6, 21, 0, tzinfo=timezone.utc)) is False
    # Saturday 2026-07-04, mid-session ET -> closed.
    assert clock.is_market_open(datetime(2026, 7, 4, 15, 0, tzinfo=timezone.utc)) is False


def test_session_day_et_boundary():
    # 01:00 UTC = prior day 21:00 ET.
    assert clock.session_day(datetime(2026, 7, 7, 1, 0, tzinfo=timezone.utc)) == "2026-07-06"


# ── certs (P0 verify: CA bundle builds) ──────────────────────────────
def test_ca_bundle_builds(sandbox):
    certs._BUNDLE = None  # reset module cache for the test
    out = certs.ensure_ca_bundle(config.CA_BUNDLE_PATH)
    assert out == config.CA_BUNDLE_PATH
    assert out.exists() and out.stat().st_size > 0
    assert "BEGIN CERTIFICATE" in out.read_text(encoding="utf-8")
