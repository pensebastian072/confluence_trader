"""Optional local-Ollama commentary for the EOD digest — OFF the trade hot path.

Local qwen2.5:7b (127.0.0.1:11434) writes a short plain-language note appended to
the Telegram EOD digest. Zero Claude-token cost. Fail-safe: Ollama down / slow /
garbage -> None, digest ships without it. This module NEVER touches plans, sizing,
or the ShadowBroker — text for the human only (guardrail #2). Ported from
robinhood_desk/desk/ollama_note.py.
"""
from __future__ import annotations

import json
import urllib.request

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "qwen2.5:7b"


def eod_note(digest: dict, timeout: int = 60) -> str | None:
    """Returns a 3-sentence desk note or None. Never raises."""
    try:
        prompt = (
            "You are a trading-desk EOD note writer. Given this JSON digest of "
            "today's paper/shadow trading activity (no live risk), write a plain "
            "3-sentence note for the PM: what happened, anything unusual, what to "
            "watch tomorrow. Do NOT advise changing sizing or overriding any gate.\n\n"
            + json.dumps(digest)
        )
        payload = json.dumps({"model": MODEL, "prompt": prompt,
                              "stream": False}).encode("utf-8")
        req = urllib.request.Request(OLLAMA_URL, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = (body.get("response") or "").strip()
        return text[:900] if text else None
    except Exception:  # noqa: BLE001 — fail-safe: no commentary
        return None
