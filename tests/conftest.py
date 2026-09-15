"""Shared fixtures — redirect every config path into tmp so tests never touch the
real cache, journal, or secrets. Pattern copied from robinhood_desk/tests/conftest.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trader import config  # noqa: E402


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point all config paths at tmp_path; create the dir layout; return it."""
    layout = {
        "BASE_DIR": tmp_path,
        "CONFIG_DIR": tmp_path / "config",
        "SECRETS_DIR": tmp_path / "secrets",
        "DATA_CACHE": tmp_path / "data_cache",
        "BARS_DIR": tmp_path / "data_cache" / "bars",
        "OPTIONS_DIR": tmp_path / "data_cache" / "options",
        "JOURNAL_DIR": tmp_path / "journal",
        "PLANS_DIR": tmp_path / "journal" / "plans",
        "POSITIONS_DIR": tmp_path / "journal" / "positions",
        "MARKS_DIR": tmp_path / "journal" / "marks",
        "RUNS_DIR": tmp_path / "journal" / "runs",
        "REPORTS_DIR": tmp_path / "journal" / "reports",
    }
    for name, path in layout.items():
        path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(config, name, path)

    files = {
        "WATCHLIST_PATH": layout["CONFIG_DIR"] / "watchlist.json",
        "ALPACA_SECRETS_PATH": layout["SECRETS_DIR"] / "alpaca.json",
        "TELEGRAM_SECRETS_PATH": layout["SECRETS_DIR"] / "telegram.json",
        "CA_BUNDLE_PATH": layout["DATA_CACHE"] / "ca_bundle.pem",
        "POSITIONS_STATE_PATH": layout["POSITIONS_DIR"] / "state.json",
        "SHADOW_PNL_PATH": layout["MARKS_DIR"] / "shadow_pnl.jsonl",
        "BASELINE_PATH": layout["JOURNAL_DIR"] / "baseline.json",
        "RESUME_FLAG_PATH": layout["JOURNAL_DIR"] / "resume.flag",
    }
    for name, path in files.items():
        monkeypatch.setattr(config, name, path)

    return {**layout, **files}
