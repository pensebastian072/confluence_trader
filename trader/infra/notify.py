"""Telegram notifier — stdlib only, fail-safe (notify failure never blocks a scan).

Secrets in gitignored secrets/telegram.json: {"bot_token": "...", "chat_id": "..."}.
ssl.create_default_context() reads the Windows cert store, so the box's
TLS-intercepting proxy verifies cleanly. Ported from
robinhood_desk/desk/telegram_notify.py.
"""
from __future__ import annotations

import json
import ssl
import urllib.request
from pathlib import Path

from .. import config


def _load_secrets(path: Path | None = None):
    try:
        data = json.loads((path or config.TELEGRAM_SECRETS_PATH).read_text(encoding="utf-8"))
        token, chat_id = data.get("bot_token"), data.get("chat_id")
        if token and chat_id:
            return {"bot_token": token, "chat_id": str(chat_id)}, None
        return None, "telegram.json missing bot_token/chat_id"
    except Exception as e:  # noqa: BLE001
        return None, f"unavailable: {e}"


def send_message(text: str, secrets_path: Path | None = None, timeout: int = 15):
    """POST sendMessage. Returns (ok, error). Never raises."""
    secrets, err = _load_secrets(secrets_path)
    if secrets is None:
        return False, err
    url = f"https://api.telegram.org/bot{secrets['bot_token']}/sendMessage"
    payload = json.dumps({"chat_id": secrets["chat_id"], "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            ok = 200 <= resp.status < 300
            return ok, None if ok else f"http {resp.status}"
    except Exception as e:  # noqa: BLE001
        return False, f"send failed: {e}"
