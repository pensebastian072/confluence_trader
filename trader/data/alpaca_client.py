"""Alpaca historical bars — the one data entry point. Paper/data only, never orders.

Free IEX feed (config.ALPACA_DATA_FEED). Every fetch returns `(df, error)` and
degrades to an empty frame rather than raising (guardrail: readers never crash the
scan). truststore (config import) makes TLS work behind the intercepting proxy.

IEX volume is a small, self-relative slice of consolidated volume — every volume
signal must stay same-feed-relative (see PLAN.md risk note).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from .. import config

# TF string -> Alpaca TimeFrame. Imported lazily so config/tests load without alpaca.
_OHLCV_COLS = ["open", "high", "low", "close", "volume"]


def _timeframe(tf: str):
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    table = {
        "1m": TimeFrame(1, TimeFrameUnit.Minute),
        "5m": TimeFrame(5, TimeFrameUnit.Minute),
        "15m": TimeFrame(15, TimeFrameUnit.Minute),
        "1h": TimeFrame(1, TimeFrameUnit.Hour),
        "4h": TimeFrame(4, TimeFrameUnit.Hour),
    }
    if tf not in table:
        raise ValueError(f"unsupported timeframe {tf!r}")
    return table[tf]


def _client():
    key, secret, _base, _paper = config.alpaca_creds()
    if not (key and secret):
        raise RuntimeError("Alpaca creds not configured (secrets/alpaca.json or APCA_* env)")
    from alpaca.data.historical import StockHistoricalDataClient
    return StockHistoricalDataClient(key, secret)


def get_bars(symbol: str, tf: str, start: datetime, end: datetime | None = None,
             feed: str | None = None) -> tuple[pd.DataFrame, str | None]:
    """Fetch OHLCV bars in [start, end]. Returns (df, error).

    df: tz-aware UTC DatetimeIndex named 'timestamp', columns open/high/low/close/
    volume, sorted, deduped. Empty df on any error (error string set). alpaca-py
    paginates internally.
    """
    end = end or datetime.now(timezone.utc)
    empty = pd.DataFrame(columns=_OHLCV_COLS)
    empty.index = pd.DatetimeIndex([], tz="UTC", name="timestamp")
    try:
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import StockBarsRequest
        feed_enum = DataFeed(feed or config.ALPACA_DATA_FEED)
        req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=_timeframe(tf),
                               start=start, end=end, feed=feed_enum)
        bars = _client().get_stock_bars(req)
    except Exception as e:  # noqa: BLE001
        return empty, f"{type(e).__name__}: {e}"

    df = bars.df
    if df is None or df.empty:
        return empty, None
    # bars.df is MultiIndex (symbol, timestamp) -> drop symbol level.
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level="symbol")
    df = df[[c for c in _OHLCV_COLS if c in df.columns]].copy()
    df.index = pd.DatetimeIndex(df.index, name="timestamp")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df, None
