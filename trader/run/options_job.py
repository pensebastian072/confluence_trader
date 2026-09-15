"""Daily post-close CBOE options snapshot job.

    python -m trader.run.options_job                 # watchlist
    python -m trader.run.options_job --symbols SPY

Fetches the delayed chain, parses to GEX/max-pain chains, caches one JSON per
symbol per day. Fail-safe: a fetch error for one symbol never aborts the rest.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from .. import config
from ..data import options_snapshot, universe
from ..infra import certs


def run(symbols=None, now=None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    certs.ensure_ca_bundle(config.CA_BUNDLE_PATH)
    symbols = symbols or universe.symbols()
    out = []
    for sym in symbols:
        raw, err = options_snapshot.fetch_raw(sym)
        if err:
            out.append({"symbol": sym, "error": err})
            continue
        parsed = options_snapshot.parse_chain(raw, now)
        options_snapshot.save(sym, parsed)
        out.append({"symbol": sym, "spot": parsed["spot"],
                    "front_expiry": parsed["front_expiry"],
                    "gex_strikes": len(parsed["gex_chain"]),
                    "pain_strikes": len(parsed["pain_chain"])})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily CBOE options snapshot.")
    ap.add_argument("--symbols", nargs="*")
    args = ap.parse_args()
    results = run(symbols=[s.upper() for s in args.symbols] if args.symbols else None)
    for r in results:
        if r.get("error"):
            print(f"  {r['symbol']:5} ERROR {r['error']}")
        else:
            print(f"  {r['symbol']:5} spot={r['spot']} exp={r['front_expiry']} "
                  f"gex={r['gex_strikes']} pain={r['pain_strikes']}")
    return 1 if any(r.get("error") for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
