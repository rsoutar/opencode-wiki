"""Path constants and shared configuration."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DAILY_DIR = ROOT_DIR / "daily"
KNOWLEDGE_DIR = ROOT_DIR / "knowledge"
CONCEPTS_DIR = KNOWLEDGE_DIR / "concepts"
CONNECTIONS_DIR = KNOWLEDGE_DIR / "connections"
QA_DIR = KNOWLEDGE_DIR / "qa"
REPORTS_DIR = ROOT_DIR / "reports"
SCRIPTS_DIR = ROOT_DIR / "scripts"
STATE_FILE = SCRIPTS_DIR / "state.json"
LAST_FLUSH_FILE = SCRIPTS_DIR / "last-flush.json"
INDEX_FILE = KNOWLEDGE_DIR / "index.md"
LOG_FILE = KNOWLEDGE_DIR / "log.md"
AGENTS_FILE = ROOT_DIR / "AGENTS.md"

COMPILE_AFTER_HOUR = 18
INTERNAL_ENV = "OPENCODE_MEMORY_INTERNAL"


def now_local() -> datetime:
    """Return the current local datetime."""
    return datetime.now().astimezone()


def now_iso() -> str:
    """Current local timestamp in ISO format."""
    return now_local().isoformat(timespec="seconds")


def today_iso() -> str:
    """Current local date."""
    return now_local().strftime("%Y-%m-%d")
