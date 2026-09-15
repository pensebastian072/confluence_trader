"""CBOE delayed-quotes options snapshot — daily post-close job source.

Public delayed endpoint (no key). Fetch is fail-safe: any error -> (None, reason),
callers degrade. Parsing is pure and unit-tested on a synthetic payload. Snapshots
cache to data_cache/options/{SYMBOL}/{YYYY-MM-DD}.json; the options_levels family
reads the latest off the hot path and drops to conf 0 when stale (> OPTIONS_STALE_DAYS).

Never trust yfinance OI (PLAN.md). GEX gamma is computed from IV+T via vendor/gex.py,
not taken from the feed.
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.request
from datetime import date, datetime, timezone

from .. import config

CBOE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"
_OCC = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")
GEX_MAX_DAYS = 45  # options within this horizon contribute to GEX


def _parse_symbol(sym: str):
    """OCC-style option symbol -> (root, expiry_date, right, strike). None if bad."""
    m = _OCC.match(sym.strip())
    if not m:
        return None
    root, ymd, right, strike8 = m.groups()
    try:
        exp = date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
    except ValueError:
        return None
    return root, exp, right, int(strike8) / 1000.0


def parse_chain(raw: dict, now: datetime | None = None) -> dict:
    """Parse a CBOE payload into GEX/max-pain chains. Never raises on bad rows."""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    data = (raw or {}).get("data") or {}
    spot = data.get("current_price") or data.get("close") or data.get("prev_day_close")
    spot = float(spot) if spot else 0.0

    # aggregate OI by (strike, expiry); keep a representative IV.
    agg: dict[tuple, dict] = {}
    for opt in data.get("options", []) or []:
        parsed = _parse_symbol(str(opt.get("option", "")))
        if parsed is None:
            continue
        _root, exp, right, strike = parsed
        t_years = max((exp - today).days, 0) / 365.0
        if t_years <= 0:
            continue
        key = (strike, exp)
        row = agg.setdefault(key, {"strike": strike, "expiry": exp.isoformat(),
                                   "t_years": t_years, "iv": 0.0,
                                   "call_oi": 0.0, "put_oi": 0.0})
        oi = float(opt.get("open_interest", 0) or 0)
        iv = float(opt.get("iv", 0) or 0)
        if right == "C":
            row["call_oi"] += oi
        else:
            row["put_oi"] += oi
        if iv > 0:
            row["iv"] = iv if row["iv"] == 0.0 else (row["iv"] + iv) / 2.0

    rows = list(agg.values())
    expiries = sorted({r["expiry"] for r in rows})
    front = expiries[0] if expiries else None
    gex_chain = [r for r in rows if r["t_years"] * 365.0 <= GEX_MAX_DAYS]
    pain_chain = [r for r in rows if r["expiry"] == front]
    return {
        "as_of": now.isoformat(),
        "snapshot_date": today.isoformat(),
        "spot": spot,
        "front_expiry": front,
        "gex_chain": gex_chain,
        "pain_chain": pain_chain,
    }


def fetch_raw(symbol: str, timeout: int = 20):
    """GET the delayed JSON. Returns (raw_dict, error). Never raises."""
    url = CBOE_URL.format(sym=symbol.upper())
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "confluence-trader/1.0"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            if not (200 <= resp.status < 300):
                return None, f"http {resp.status}"
            return json.loads(resp.read().decode("utf-8")), None
    except Exception as e:  # noqa: BLE001
        return None, f"fetch failed: {e}"


def snapshot_path(symbol: str, day: str):
    return config.OPTIONS_DIR / symbol.upper() / f"{day}.json"


def save(symbol: str, parsed: dict) -> None:
    p = snapshot_path(symbol, parsed["snapshot_date"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(parsed), encoding="utf-8")


def load_latest(symbol: str, now: datetime | None = None):
    """Newest cached snapshot -> (parsed, age_days, error). Fail-safe."""
    now = now or datetime.now(timezone.utc)
    d = config.OPTIONS_DIR / symbol.upper()
    try:
        files = sorted(d.glob("*.json"))
    except Exception:  # noqa: BLE001
        files = []
    if not files:
        return None, None, "no snapshot"
    try:
        parsed = json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return None, None, f"unreadable: {e}"
    try:
        snap_day = date.fromisoformat(parsed.get("snapshot_date"))
        age = (now.date() - snap_day).days
    except Exception:  # noqa: BLE001
        age = None
    return parsed, age, None
