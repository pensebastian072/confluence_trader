"""Central config: paths, timeframes, thresholds, regime-keyed weights, creds.

One module owns every path, knob, and weight so no other module hardcodes them.
Doctrine (PLAN.md): paper/shadow only, LLM never on the hot path, weights are
hyperparameters swept in walk-forward — the presets here are a-priori defaults,
NOT fitted on full history. Changing them is a deliberate model-version bump.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Route stdlib ssl (and thus requests / alpaca-py) through the OS trust store so
# pulls work behind this box's TLS-intercepting proxy/AV. No-op if truststore is
# missing. This is the runtime analogue of pip --native-tls.
try:
    import truststore as _truststore
    _truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass

try:
    from dotenv import load_dotenv
except Exception:  # noqa: BLE001
    def load_dotenv(*_a, **_k):  # type: ignore
        return False

# ── Paths ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")  # APCA_* creds etc; no-op if absent

CONFIG_DIR = BASE_DIR / "config"
SECRETS_DIR = BASE_DIR / "secrets"
DATA_CACHE = BASE_DIR / "data_cache"
BARS_DIR = DATA_CACHE / "bars"
OPTIONS_DIR = DATA_CACHE / "options"
JOURNAL_DIR = BASE_DIR / "journal"
PLANS_DIR = JOURNAL_DIR / "plans"
POSITIONS_DIR = JOURNAL_DIR / "positions"
MARKS_DIR = JOURNAL_DIR / "marks"
RUNS_DIR = JOURNAL_DIR / "runs"
REPORTS_DIR = JOURNAL_DIR / "reports"

WATCHLIST_PATH = CONFIG_DIR / "watchlist.json"
ALPACA_SECRETS_PATH = SECRETS_DIR / "alpaca.json"
TELEGRAM_SECRETS_PATH = SECRETS_DIR / "telegram.json"
CA_BUNDLE_PATH = DATA_CACHE / "ca_bundle.pem"

POSITIONS_STATE_PATH = POSITIONS_DIR / "state.json"
SHADOW_PNL_PATH = MARKS_DIR / "shadow_pnl.jsonl"
BASELINE_PATH = JOURNAL_DIR / "baseline.json"

for _d in (CONFIG_DIR, DATA_CACHE, BARS_DIR, OPTIONS_DIR, PLANS_DIR,
           POSITIONS_DIR, MARKS_DIR, RUNS_DIR, REPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Timeframes ───────────────────────────────────────────────────────
BASE_TF = "1m"                       # fetched from Alpaca; higher TFs derived locally
TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h")
SETUP_TFS = ("5m", "15m")            # where setups are detected
BIAS_TFS = ("1h", "4h")             # higher-TF bias veto
TRIGGER_TF = "1m"                    # entry trigger + exits only
# Resample retention (days); 1h/4h fetched deep for history.
RETENTION_DAYS = {"1m": 90, "5m": 1095, "15m": 1095, "1h": 3650, "4h": 3650}
# Right-labeled / right-closed resample; anchor fixed once here, never change silently.
RESAMPLE_CLOSED = "right"
RESAMPLE_LABEL = "right"

# ── Emit gate (scorer) ───────────────────────────────────────────────
EMIT_MIN_COMBINED = 0.6              # |combined confluence| threshold
MIN_FAMILIES_AGREE = 3              # families agreeing on sign
PLAN_TTL_SETUP_BARS = 3            # expires_at = 3 setup-TF bars

# ── Regime-keyed weight presets (a-priori; swept in walk-forward) ────
# family -> weight, per coarse regime bucket (ADX + ATR-percentile derived).
SIGNAL_FAMILIES = ("momentum", "volume_flow", "smc_orderflow",
                   "options_levels", "patterns", "fibonacci")
REGIME_WEIGHTS = {
    "trend": {"momentum": 1.4, "volume_flow": 1.0, "smc_orderflow": 1.2,
              "options_levels": 0.8, "patterns": 0.8, "fibonacci": 1.0},
    "chop": {"momentum": 0.6, "volume_flow": 1.0, "smc_orderflow": 1.2,
             "options_levels": 1.2, "patterns": 1.2, "fibonacci": 1.2},
    "transitional": {"momentum": 1.0, "volume_flow": 1.0, "smc_orderflow": 1.0,
                     "options_levels": 1.0, "patterns": 1.0, "fibonacci": 1.0},
}
DEFAULT_REGIME = "transitional"

# ── R:R plan / sizing (jesse math; paper) ────────────────────────────
R_USD = 100.0                        # $100 = 1R (paper)
TP_MULTIPLES = (1.0, 2.0, 4.0)      # tp1/tp2/tp3 in R
TP_FRACTIONS = (0.4, 0.3, 0.3)      # scale-out fractions
STOP_ATR_BUFFER = 0.25              # stop beyond opposing swing/OB by 0.25*ATR
LEVEL_SNAP_TOLERANCE_PCT = 0.003    # snap TP to a confluent level if within 0.3%

# ── ShadowBroker ─────────────────────────────────────────────────────
SLIPPAGE_BPS = 2                     # base fill slippage; sensitivity 5/10 in backtest
SLIPPAGE_BPS_SENSITIVITY = (5, 10)

# ── Protections (freqtrade-shaped) ───────────────────────────────────
DAILY_LOSS_HALT_R = -3.0            # halt after -3R on the day
MAX_OPEN_POSITIONS = 3
MAX_PENDING_ORDERS = 2
MAX_PER_SYMBOL = 1
COOLDOWN_BARS_AFTER_STOP = 4       # setup-TF bars per-symbol cooldown after stop-out
STOPOUT_BURST_N = 3                 # >=3 stop-outs / 2h ...
STOPOUT_BURST_WINDOW_H = 2
GLOBAL_COOLDOWN_H = 4              # ... -> 4h global cooldown
EQUITY_KILL_DRAWDOWN_PCT = 6.0     # -6% from peak -> kill switch (manual resume.flag)
RESUME_FLAG_PATH = JOURNAL_DIR / "resume.flag"

# ── Data freshness ───────────────────────────────────────────────────
OPTIONS_STALE_DAYS = 3             # snapshot older than this -> options family conf 0
MIN_ROUND_TRIPS_TO_TRUST = 30      # gate evidence threshold

# ── Market session (ET) ──────────────────────────────────────────────
MARKET_TZ = "America/New_York"
SESSION_OPEN = (9, 30)
SESSION_CLOSE = (16, 0)
EOD_FLAT = (15, 55)                 # v1 EOD flat time

# ── Alpaca ───────────────────────────────────────────────────────────
ALPACA_PAPER_BASE = "https://paper-api.alpaca.markets/v2"
ALPACA_DATA_FEED = "iex"           # free tier; IEX volume is self-relative only


def alpaca_creds() -> tuple[str | None, str | None, str, bool]:
    """(key_id, secret_key, base_url, paper). Prefers APCA_* env (.env), then
    secrets/alpaca.json. Returns (None, None, ...) if unconfigured — callers
    degrade rather than raise. Paper-only: base_url is forced to the paper host."""
    key = os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY")
    base = os.environ.get("APCA_API_BASE_URL", ALPACA_PAPER_BASE)
    if not (key and secret) and ALPACA_SECRETS_PATH.exists():
        try:
            data = json.loads(ALPACA_SECRETS_PATH.read_text(encoding="utf-8"))
            key = key or data.get("key_id") or data.get("api_key")
            secret = secret or data.get("secret_key") or data.get("api_secret")
            base = data.get("base_url", base)
        except Exception:  # noqa: BLE001
            pass
    # Hard paper guardrail: never point at the live endpoint.
    paper = "paper-api" in (base or "")
    if not paper:
        base = ALPACA_PAPER_BASE
        paper = True
    return key, secret, base, paper


def load_watchlist() -> list[str]:
    """Symbols to scan. Falls back to SPY/QQQ if the file is absent/corrupt."""
    try:
        data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
        syms = data.get("symbols") if isinstance(data, dict) else data
        if isinstance(syms, list) and syms:
            return [str(s).upper() for s in syms]
    except Exception:  # noqa: BLE001
        pass
    return ["SPY", "QQQ"]
