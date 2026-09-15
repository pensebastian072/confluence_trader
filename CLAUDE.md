# confluence_trader — agent guide

Standalone multi-signal **MTF confluence trading engine**. Combines momentum,
volume/flow, SMC order-flow, options levels, chart patterns, fibonacci, and market
structure across 1m/5m/15m/1h/4h into one trade conclusion with laddered R:R plans,
validated behind a walk-forward research gate. **The trading brain only — broker
integration is deliberately out of scope.**

Full build plan + phase map + resume pointer: **`PLAN.md`** (read it first).

## Hard rules (non-negotiable — violating any = stop and ask)

1. **Paper / shadow ONLY.** No live broker, no real order routing, no live keys.
   Execution goes through `ShadowBroker` (simulated fills). Alpaca is a **data**
   source only, and only ever the **paper** endpoint (`config.alpaca_creds()`
   forces `paper-api`, refuses the live host).
2. **LLM / Ollama NEVER on the trade hot path.** Models reach the decision path
   only via a flag-file read through `infra/failsafe.read_flag`, which fails safe:
   missing/stale → neutral, never a block or size-up. Ollama is EOD text only.
3. **Deterministic engine has final say.** The scorer + protections are the only
   things that emit or block a plan. No model output sizes a trade.
4. **New signal family / weight set stays SHADOW until the research gate clears**
   (pooled OOS WR ≥50% AND expectancy >0 AND PBO <0.5 AND DSR >0). First pass is
   expected to FAIL — that's the system working. Load skill `quant-research-gate`
   before touching the gate or any model/weights.
5. **No look-ahead.** `mtf/merge.merge_informative` shifts higher-TF columns one bar
   before merging. The truncation-invariance test (P2) gates every later phase; a
   change that fails it does not ship.
6. **Weights are hyperparameters, not hand-tuned.** `config.REGIME_WEIGHTS` are
   a-priori defaults swept only through walk-forward folds — never edited post-hoc
   on full history. Changing a default is a model-version bump.
7. Dashboards (later) bind **127.0.0.1 only**; never expose, never tunnel.

## Environment (this box — see skill `win-quant-env`)

- Python 3.11 in `.venv` (uv-managed). Use `.venv\Scripts\python.exe` — bare
  `python` is the Store stub.
- **TLS interception**: `config.py` calls `truststore.inject_into_ssl()` at import
  (runtime analogue of pip `--native-tls`); `infra/certs.ensure_ca_bundle()` builds
  a Windows-store CA bundle for any libcurl-based lib. `uv sync --native-tls`;
  `uv pip install --native-tls ...`.
- **smartmoneyconcepts** is NOT installed — it pins pandas==2.0.2, incompatible
  with this repo's pandas 3.x. The vendored `vendor/smc_fallback.py` (own, leak-safe
  FVG/structure primitives) is the PRIMARY path, not just a fallback. Re-evaluate the
  lib only if it ever ships a pandas-3-compatible release.
- git: no global identity — commit with
  `git -c user.email='YOUR_GITHUB_NOREPLY_EMAIL' -c user.name='YOUR_GITHUB_USERNAME'`,
  straight to `main`; retry `git add` if Norton locks `.git/objects`.

## Secrets

- `secrets/alpaca.json` (`{"key_id", "secret_key", "base_url"}`) — canonical
  paper-data creds, already set. `config.alpaca_creds()` also honours `APCA_*` env
  (from an optional `.env`) if present, env first. Gitignored — never commit/log.
- `secrets/telegram.json` = `{"bot_token": "...", "chat_id": "..."}` for digests.

## Verification

- Tests (no network): `.venv\Scripts\python.exe -m pytest -q`
- Tests incl. live sources: `.venv\Scripts\python.exe -m pytest -m network`

## Before committing

Load skill `paper-trading-guardrails` before editing engine/exec/data/LLM code.
Run the `quant-reviewer` subagent before committing changes to
scorer / plan / exits / protections / execution.
