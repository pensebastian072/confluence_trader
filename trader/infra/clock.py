"""Market clock — ET session helpers. Local-timezone-agnostic (uses ZoneInfo).

Regular US equity session only (09:30-16:00 ET), no holiday calendar in v1 —
callers that need holiday-awareness use the Alpaca calendar at the data layer.
All functions are pure given `now`.
"""
from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from .. import config

_TZ = ZoneInfo(config.MARKET_TZ)


def now_et(now: datetime | None = None) -> datetime:
    """Current time in market TZ. `now` may be naive (assumed UTC) or aware."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(_TZ)


def _at(hm: tuple[int, int]) -> time:
    return time(hm[0], hm[1])


def is_weekday(now: datetime | None = None) -> bool:
    return now_et(now).weekday() < 5


def is_market_open(now: datetime | None = None) -> bool:
    """Regular session, weekday only. Holidays not modelled here (v1)."""
    et = now_et(now)
    if et.weekday() >= 5:
        return False
    return _at(config.SESSION_OPEN) <= et.time() < _at(config.SESSION_CLOSE)


def is_after_eod_flat(now: datetime | None = None) -> bool:
    et = now_et(now)
    return et.time() >= _at(config.EOD_FLAT)


def session_day(now: datetime | None = None) -> str:
    """ET calendar day key, YYYY-MM-DD — the day-boundary used for journals."""
    return now_et(now).strftime("%Y-%m-%d")
