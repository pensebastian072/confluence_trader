"""Trading universe + per-timeframe backfill windows.

v1 universe = the watchlist (SPY/QQQ). Retention windows (config.RETENTION_DAYS)
define how far back each timeframe backfills: 1m 90d, 5m/15m 3y, 1h/4h 10y.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .. import config


def symbols() -> list[str]:
    return config.load_watchlist()


def timeframes() -> tuple[str, ...]:
    return config.TIMEFRAMES


def backfill_start(tf: str, now: datetime | None = None) -> datetime:
    """Earliest timestamp to backfill for a timeframe, per retention policy."""
    now = now or datetime.now(timezone.utc)
    days = config.RETENTION_DAYS.get(tf, 365)
    return now - timedelta(days=days)
