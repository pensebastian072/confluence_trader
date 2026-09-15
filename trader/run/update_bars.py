"""Incremental bar updater. Fetches OHLCV for the universe across all timeframes
and merges into the parquet cache. Idempotent — a second run over the same window
adds nothing.

    python -m trader.run.update_bars                  # incremental from last cached bar
    python -m trader.run.update_bars --backfill       # full retention window per tf
    python -m trader.run.update_bars --symbols SPY --tf 1m 5m

Free IEX historical restricts the most-recent ~15 min, so `end` is capped at
now-16min to avoid subscription errors.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from .. import config
from ..data import alpaca_client, bar_store, universe
from ..infra import certs

RECENT_CUTOFF = timedelta(minutes=16)  # free IEX: last ~15 min withheld


def update_one(symbol: str, tf: str, backfill: bool, now: datetime) -> dict:
    end = now - RECENT_CUTOFF
    if backfill:
        start = universe.backfill_start(tf, now)
    else:
        last = bar_store.last_timestamp(symbol, tf)
        start = last if last is not None else universe.backfill_start(tf, now)
    if start >= end:
        return {"symbol": symbol, "tf": tf, "skipped": "up-to-date"}
    df, err = alpaca_client.get_bars(symbol, tf, start, end)
    if err:
        return {"symbol": symbol, "tf": tf, "error": err}
    stats = bar_store.merge_upsert(symbol, tf, df)
    stats.update(symbol=symbol, tf=tf, fetched=len(df))
    return stats


def run(symbols=None, tfs=None, backfill=False, now=None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    certs.ensure_ca_bundle(config.CA_BUNDLE_PATH)
    symbols = symbols or universe.symbols()
    tfs = tfs or list(universe.timeframes())
    results = []
    for sym in symbols:
        for tf in tfs:
            results.append(update_one(sym, tf, backfill, now))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="Update the OHLCV parquet cache.")
    ap.add_argument("--symbols", nargs="*", help="override watchlist")
    ap.add_argument("--tf", nargs="*", help="override timeframes")
    ap.add_argument("--backfill", action="store_true", help="full retention window")
    args = ap.parse_args()
    results = run(symbols=[s.upper() for s in args.symbols] if args.symbols else None,
                  tfs=args.tf, backfill=args.backfill)
    for r in results:
        if r.get("error"):
            print(f"  {r['symbol']:5} {r['tf']:>3}  ERROR {r['error']}")
        elif r.get("skipped"):
            print(f"  {r['symbol']:5} {r['tf']:>3}  {r['skipped']}")
        else:
            print(f"  {r['symbol']:5} {r['tf']:>3}  +{r['added']} upd{r['updated']} "
                  f"total={r['total']} (fetched {r['fetched']})")
    return 1 if any(r.get("error") for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
