# Plan: `confluence_trader` — standalone AI trading engine (paper/shadow only)

Status 2026-07-07: plan approved, build barely started (P0 in progress — repo tree, git init,
.gitignore, pyproject.toml exist; nothing else). Resume at P0: config.py, infra ports, CLAUDE.md,
sandbox fixture, venv (`uv sync --native-tls`).

## Context

User wants the best-possible AI trader as its own repo — the **trading brain itself**; broker
integration explicitly deferred. It must combine, in one trade conclusion: momentum, volume,
order flow, options levels, chart patterns, fibonacci, and chart/market structure — across
1m/5m/15m/1h/4h for entries AND exits, with R:R plans laddered 1R→4R and a **win-rate ≥50%
validation gate** (a gate, never a promise). GitHub was scanned; verdicts below are from live
review of the repos. Standing doctrine applies: paper/advisory only, LLM never on the hot path,
shadow until the research gate clears (PBO<0.5, DSR>0), dashboards 127.0.0.1 only.

Repo: **`C:\Users\<your-user>\confluence_trader`** (own git repo, commit to main with explicit
`-c user.email/-c user.name`, Norton git-lock retry loop).

## Dependencies (from GitHub scan)

| Piece | Pick | Why |
|---|---|---|
| Indicators | `pandas-ta-classic` (MIT, active 2026) | original pandas-ta now paid/gone; pure-python, no compiler |
| SMC/order-flow proxy | `smartmoneyconcepts` (MIT, pinned 0.0.26) | fvg/ob/bos_choch/liquidity/swings; vendor single-file fallback `vendor\smc_fallback.py` day 1 |
| Backtest loop | `backtesting.py` (MIT) — or own "replay mode" reusing ShadowBroker (likely winner, decide P8) | event-driven bar loop |
| Walk-forward/gate | **port `copper_brain\copper_brain\validate.py`** (pbo_cscv, deflated_sharpe, evaluate_gate, walk_forward_splits) | canonical, don't reinvent |
| Volume profile / fib / GEX | write own (~30/~20/~100 lines; BS gamma via `math.erf`) | no good OSS; gex-tracker = formula reference only |
| Patterns | own swing-geometry rules on the shared swing engine | stock-pattern is GPL (reference only) |
| Data | **Alpaca free** (primary, ~10y 1m bars; **user must create free key** → `secrets\alpaca.json`) + CBOE delayed EOD options JSON (OI/GEX) + yfinance last-resort | yfinance alone unreliable; never trust yfinance OI |
| Architecture patterns | freqtrade (reimplement clean — GPL): MTF merge-with-shift, protections layer, dry-run wallet; jesse (MIT): plan lifecycle + sizing math; TradingAgents: committee/veto concept only, later | |

## Repo layout

```
confluence_trader\
  CLAUDE.md  pyproject.toml (uv, py3.11, pinned)  config\watchlist.json
  trader\
    config.py                  # all paths/thresholds/weights, one module
    infra\   failsafe.py journal.py certs.py notify.py ollama_note.py clock.py
    data\    alpaca_client.py bar_store.py options_snapshot.py universe.py
    mtf\     resample.py merge.py
    signals\ base.py swings.py momentum.py volume_flow.py volume_profile.py
             smc_orderflow.py options_levels.py patterns.py fibonacci.py
    engine\  regime.py scorer.py plan.py exits.py protections.py sizing.py
    exec\    shadow_broker.py marks.py
    run\     update_bars.py scan.py options_job.py eod.py
    backtest\ features.py bt_adapter.py walkforward.py gate.py report.py
    vendor\  smc_fallback.py gex.py
  secrets\ (gitignored: alpaca.json, telegram.json)
  data_cache\bars\{SYM}\{tf}.parquet   data_cache\options\{SYM}\{date}.json
  journal\ plans\{day}.jsonl positions\state.json marks\shadow_pnl.jsonl runs\ reports\
  scripts\ register_tasks.ps1 + VBS->PS->python.exe hidden-launch chain (ASCII-only)
  tests\  conftest.py (sandbox fixture) fixtures\synthetic.py test_*.py
```

## Core design

**Data**: fetch 1m from Alpaca (IEX feed), derive 5m/15m/1h/4h locally via one tested
resampler (right-labeled/right-closed). Retention: 1m 90d, 5m/15m 3y, 1h/4h 10y (1h fetched
direct for deep history). Parquet append-only merge, atomic replace, idempotent `update()`.
Options: daily post-close CBOE snapshot job; stale >3d → options family confidence 0.
Every reader returns `(data, error)`, degrades neutral, never raises.

**MTF no-look-ahead merge** (build first, test hardest): `merge_informative()` shifts
higher-TF columns by one bar then merge_asof/ffill onto base TF — a 4h candle's values are
visible only after it closes. Two key tests: golden visibility test + **truncation-invariance
test parametrized over every family's populate()** (recompute on truncated history, row at t
must be bit-identical) — the leakage killer, gate for all later phases.

**Six signal families, one contract** — `populate(df, tf) -> df` adds `f_{family}_score`
[-1,+1], `f_{family}_conf` [0,1], tags + named levels; fully vectorized; failure → (0,0):
1. `momentum` — RSI/MACD/ADX/EMA-stack blend (pandas-ta-classic), ADX-scaled confidence.
2. `volume_flow` — OBV divergence, MFI, anchored VWAP, relative volume, POC/VAH/VAL profile.
3. `smc_orderflow` — market structure + order-flow proxy: bos_choch, FVGs, order blocks,
   liquidity pools; shared swing engine `swings.py` (wraps smc.swing_highs_lows) feeds
   patterns + fib too.
4. `options_levels` — GEX (own BS gamma), zero-gamma flip, max pain, OI walls from CBOE
   snapshot; daily levels ffilled onto intraday via the shifted merge; conf decays with age.
5. `patterns` — own geometry on swing pivots: H&S, double top/bottom, triangles, S/R zones
   (>=3 touches); fires on completion only.
6. `fibonacci` — retrace grid (.382/.5/.618/.786) + extensions off last completed swing leg;
   levels also feed target snapping.

**Scorer** (`engine\scorer.py`): `combined = Σ w·score·conf / Σ w·conf` (absent families drop
out); weights are **regime-keyed presets** (trend/chop/transitional via ADX+ATR percentile) and
are hyperparameters swept in walk-forward — never hand-tuned on full history. Emit requires:
|combined| >= 0.6, >=3 families agreeing, 1h+4h bias not opposing, regime gate, no protection
lock. Setup TFs = 5m and 15m; 1m = entry trigger + exits only.

**TradePlan** (frozen dataclass, journaled append-only, ticket_builder discipline): entry
(limit at close/pullback level), structure stop (beyond opposing swing/OB ± 0.25·ATR),
qty = r_usd/(entry−stop) (jesse math, $100 = 1R paper), tp1/tp2/tp3 = +1R/+2R/+4R snapped to
confluent levels (VAH/fib ext/OI wall) when within tolerance, fractions (0.4,0.3,0.3), full
per-family score breakdown for explainability, TTL `expires_at` = 3 setup-TF bars. Both sides
generated (all shadow); gate evaluates per side.

**Exits** (priority order, deterministic, same code live+backtest): hard stop (same-bar
stop+target → **stop first**, conservative); tp1→close 40% + BE stop; tp2→close 30% + trail
behind setup-TF swing; tp3 runner; CHoCH-against → market exit; time stop 24 setup-TF bars to
tp1; EOD flat 15:55 ET v1 (swing variants later).

**ShadowBroker** (the one execution interface; real broker later, out of scope): limit fill on
1m touch + slippage in bps (2, sensitivity row at 5/10 — never absolute), state via atomic
write_state, closed trades → `shadow_pnl.jsonl` = the gate's evidence stream (>=30 round-trips
before believing anything).

**Protections** (freqtrade-shaped, composable, each → (locked, until, reason), all journaled):
daily loss halt −3R; <=3 open + <=2 pending, 1/symbol; per-symbol cooldown 4 setup-TF bars after
stop-out; >=3 stop-outs/2h → global 4h cooldown; equity −6% from peak → kill switch needing
manual `resume.flag`; stale-data → skip symbol.

**Validation harness — no-drift rule**: `backtest\features.py::build_features()` is THE single
pipeline (resample → populate ×6 → shifted merges → regime → combine) used by live scan (last
row) and backtest (full history). Walk-forward: expanding splits (ported), grid <= ~30 trials
(weight presets × threshold × n_agree), select on train only, pool OOS trades; gate = ported
PBO/DSR with honest n_trials. **Acceptance: pooled OOS WR >=50% AND expectancy >0 AND PBO<0.5
AND DSR>0 — else stays SHADOW and iterate.** WR defined precisely: closed plan total pnl>0.
Expect first-pass FAIL; that's the system working.

**Scheduler**: copy robinhood_desk template — non-elevated tasks, `ConfluenceTrader-Scan`
(09:31 ET, every 5 min × 6.5h; recompute higher-TF families only on new candle close),
`-Options` 16:45, `-EOD` 16:20 (Telegram digest + fail-safe Ollama note). First-run baseline
anti-replay (emit nothing on first scan; plans only from bars newer than baseline).

## Files to reuse (verified paths)

- `copper_brain\copper_brain\validate.py` — port gate + splits into `trader\backtest\gate.py`
- `robinhood_desk\desk\ticket_builder.py` — write_state/append_jsonl/fold/expire shapes
- `robinhood_desk\desk\telegram_notify.py` — send_message transport verbatim; new formatters
- `robinhood_desk\desk\ollama_note.py` — EOD note pattern
- `robinhood_desk\tests\conftest.py` — sandbox fixture pattern, copy exactly
- `robinhood_desk\scripts\register_desk_tasks.ps1` + `_run_desk_tick.vbs` — scheduler template

## Build phases (each ends verified)

| P | Scope | Verify |
|---|---|---|
| 0 | scaffold, venv (uv --native-tls), infra ports, CLAUDE.md rules, sandbox fixture | pytest green; CA bundle builds; Telegram test send |
| 1 | **user: free Alpaca keys → secrets\alpaca.json**; data layer + backfill SPY/QQQ | cache exists all TFs; second update idempotent; spot-check vs chart |
| 2 | resample + merge + leakage suite | truncation-invariance + golden visibility green — hard gate |
| 3 | swings, momentum, volume_flow(+profile), smc_orderflow + synthetic fixtures | planted-structure detector tests; per-family truncation test |
| 4 | fibonacci, patterns, options job + vendor\gex.py + options_levels | pattern tests; real SPY CBOE snapshot; GEX/max-pain sanity vs public ref |
| 5 | regime, scorer, plan, sizing, exits | determinism + R-math tests; golden 30-day SPY slice → committed expected plans |
| 6 | ShadowBroker, protections, journal, eod digest | broker/protection tests; `scan --dry-run` then `--once` clean; digest on Telegram |
| 7 | scripts + task registration, market-hours, baseline | tasks registered; >=3 trading days unattended clean shadow scans |
| 8 | features.py shared path, backtest (bt_adapter or replay), walk-forward, gate, report | backtest matches live decisions bit-for-bit on overlap; 3y walk-forward report |
| 9 | verdict vs acceptance; iterate weights/families through harness only | gate_status.json; PASS→still shadow (broker out of scope) / FAIL→documented iteration |

Run `quant-reviewer` before commits touching scorer/plan/exits/protections; load
`quant-research-gate` skill before P8-9; `win-quant-env` before installs/tasks.

## Key risks (designed-for)

- **IEX volume bias** (Alpaca free ~2-3% consolidated volume): all volume signals self-relative
  on same feed; verify at P1 whether free tier serves SIP for >15-min-old history (if yes, use
  SIP for cache).
- CBOE endpoint fragility → conf-decay + conf=0 fallback already in design.
- Weight overfit → grid through folds only, honest n_trials in DSR, no post-hoc edits.
- 4R ladder vs WR>=50% tension → WR definition fixed in report.py (pnl>0 incl. BE scratches).
- 4h resample anchor convention: pick once at P2, unit-test, never change silently.
- smartmoneyconcepts 0.0.x pin risk → vendored fallback + one-line import indirection.

## Verification (end-to-end)

1. `.venv\Scripts\python.exe -m pytest -q` — full suite green.
2. `python -m trader.run.update_bars` twice — idempotent.
3. `python -m trader.run.scan --dry-run` then `--once` — journaled plans, no exceptions,
   Telegram alert arrives.
4. Golden-slice regression: fixed SPY slice reproduces committed plan list.
5. P8: backtest decisions == live-shadow decisions on overlapping window, bit-for-bit.
6. Walk-forward report generated with WR/expectancy/PF/DSR/PBO + verdict.
