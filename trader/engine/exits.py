"""Deterministic exit engine — identical code live and in backtest.

Priority per bar (conservative, fixed order):
  1. Hard stop. If stop and a target are both touched in the same bar, the STOP
     wins (worst-case fill assumption).
  2. TP1 -> scale out TP_FRACTIONS[0], move stop to break-even.
  3. TP2 -> scale out TP_FRACTIONS[1], trail stop to TP1.
  4. TP3 -> close the runner.
  5. CHoCH-against -> market-exit the remainder.
  6. Time stop -> if TP1 not reached within TIME_STOP_BARS setup-TF bars, exit.
  7. EOD flat -> close the remainder.

`position` is a plain dict mutated through a copy; `process_bar` returns
(new_position, events). remaining_frac 0 means the position is closed.
"""
from __future__ import annotations

TIME_STOP_BARS = 24


def open_position(plan) -> dict:
    return {
        "side": plan.side, "entry": plan.entry, "stop": plan.stop,
        "tp1": plan.tp1, "tp2": plan.tp2, "tp3": plan.tp3,
        "fractions": list(plan.tp_fractions),
        "remaining_frac": 1.0, "tp1_done": False, "tp2_done": False,
        "tp3_done": False, "be_moved": False, "bars_since_entry": 0, "closed": False,
    }


def _hit(side: str, level: float, bar: dict, kind: str) -> bool:
    """Whether `level` is touched this bar. kind: 'stop' or 'target'."""
    if side == "long":
        return bar["low"] <= level if kind == "stop" else bar["high"] >= level
    return bar["high"] >= level if kind == "stop" else bar["low"] <= level


def process_bar(position: dict, bar: dict) -> tuple[dict, list[dict]]:
    pos = dict(position)
    events: list[dict] = []
    if pos["closed"] or pos["remaining_frac"] <= 0:
        return pos, events
    side = pos["side"]

    # 1. hard stop (checked first -> conservative on same-bar stop+target)
    if _hit(side, pos["stop"], bar, "stop"):
        events.append({"type": "STOP", "price": pos["stop"], "portion": pos["remaining_frac"]})
        pos["remaining_frac"] = 0.0
        pos["closed"] = True
        pos["bars_since_entry"] += 1
        return pos, events

    # 2-4. take-profits (in order, may cascade within one bar)
    if not pos["tp1_done"] and _hit(side, pos["tp1"], bar, "target"):
        events.append({"type": "TP1", "price": pos["tp1"], "portion": pos["fractions"][0]})
        pos["remaining_frac"] = max(0.0, pos["remaining_frac"] - pos["fractions"][0])
        pos["tp1_done"] = True
        pos["stop"] = pos["entry"]           # move to break-even
        pos["be_moved"] = True
    if not pos["tp2_done"] and _hit(side, pos["tp2"], bar, "target"):
        events.append({"type": "TP2", "price": pos["tp2"], "portion": pos["fractions"][1]})
        pos["remaining_frac"] = max(0.0, pos["remaining_frac"] - pos["fractions"][1])
        pos["tp2_done"] = True
        pos["stop"] = pos["tp1"]             # trail to TP1
    if not pos["tp3_done"] and _hit(side, pos["tp3"], bar, "target"):
        events.append({"type": "TP3", "price": pos["tp3"], "portion": pos["remaining_frac"]})
        pos["remaining_frac"] = 0.0
        pos["tp3_done"] = True
        pos["closed"] = True

    # 5. CHoCH against the position
    if not pos["closed"] and bar.get("choch_against") and pos["remaining_frac"] > 0:
        events.append({"type": "CHOCH", "price": bar["close"], "portion": pos["remaining_frac"]})
        pos["remaining_frac"] = 0.0
        pos["closed"] = True

    # 6. time stop (only if TP1 never reached)
    if not pos["closed"] and not pos["tp1_done"] and pos["bars_since_entry"] + 1 >= TIME_STOP_BARS:
        events.append({"type": "TIME", "price": bar["close"], "portion": pos["remaining_frac"]})
        pos["remaining_frac"] = 0.0
        pos["closed"] = True

    # 7. EOD flat
    if not pos["closed"] and bar.get("is_eod") and pos["remaining_frac"] > 0:
        events.append({"type": "EOD", "price": bar["close"], "portion": pos["remaining_frac"]})
        pos["remaining_frac"] = 0.0
        pos["closed"] = True

    pos["bars_since_entry"] += 1
    return pos, events
