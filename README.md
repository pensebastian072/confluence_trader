# confluence_trader

A multi-timeframe **confluence** trading engine: the decision brain only, with
broker integration deliberately out of scope.

Most retail strategy code fuses one signal to one timeframe and calls it a
system. This engine combines seven signal families — momentum, volume/flow,
smart-money-concept order flow, options levels, chart patterns, fibonacci, and
market structure — across 1m / 5m / 15m / 1h / 4h into a single trade conclusion
with a laddered risk-reward plan, and then puts the whole thing behind a
walk-forward research gate that it is expected to fail on the first pass.

## Design rules

These are hard constraints, not preferences:

1. **Paper / shadow only.** No live broker, no order routing, no live keys.
   Simulated fills go through a `ShadowBroker`. The market-data vendor is a
   *data* source only, and the config layer forces the paper endpoint and
   refuses the live host outright.
2. **No LLM on the trade hot path.** Models reach the decision path only through
   a flag file read by a fail-safe helper: missing or stale input resolves to
   neutral, never to a block and never to a size-up. Language models are used for
   end-of-day text only.
3. **The deterministic engine has final say.** The scorer and the protection
   layer are the only things that can emit or block a plan. No model output ever
   sizes a trade.
4. **A new signal family or weight set stays SHADOW until the gate clears** —
   pooled out-of-sample win rate ≥ 50%, expectancy > 0, Probability of Backtest
   Overfitting < 0.5, and Deflated Sharpe Ratio > 0. The first pass is expected
   to fail. That is the system working, not a defect.
5. **No look-ahead.** Higher-timeframe columns are shifted one bar before being
   merged down. A truncation-invariance test gates every later phase: a change
   that fails it does not ship.
6. **Weights are hyperparameters, not hand-tuned values.** Regime weights are
   a-priori defaults swept only through walk-forward folds, never edited
   post-hoc against full history. Changing a default is a model-version bump.
7. **Any dashboard binds to loopback only.** Never exposed, never tunnelled.

## Layout

- `trader/signals/` — the signal families, one module each
- `trader/mtf/` — multi-timeframe merge, with the look-ahead shift
- `trader/engine/` — scorer, regime detection, plan construction, sizing, exits
- `trader/backtest/` — walk-forward harness
- `trader/exec/` — shadow broker, simulated fills
- `trader/infra/` — fail-safe flag reads, config
- `tests/`, `tests/golden/` — unit and golden-output tests
- `PLAN.md` — the full build plan and phase map
- `config/` — regime weights and thresholds

## Status — read this before using anything here

**The engine is built but not validated.** The signal families, the MTF merge,
the scorer, regime detection, sizing and the exit ladder all exist and have
tests. What has *not* happened is the walk-forward validation run that the whole
design exists to be judged by.

So there is no performance claim in this README, because there is no result yet.
Nothing here has cleared the gate, nothing is promoted, and the honest
expectation — given every other strategy tested on the same bench — is that the
first walk-forward pass comes back negative.

`PLAN.md` was written before the engine was built and understates what is on
disk; treat the layout above as the current state.

See [`DISCLAIMER.md`](DISCLAIMER.md). Not investment advice. MIT licensed.
