"""Summarize a recent session delta into today's daily log."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from config import COMPILE_AFTER_HOUR, DAILY_DIR, LAST_FLUSH_FILE, ROOT_DIR, SCRIPTS_DIR, now_iso, now_local
from opencode_runner import run_opencode
from utils import file_hash, load_state

LOG_FILE = SCRIPTS_DIR / "flush.log"

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def load_flush_state() -> dict:
    """Load the last flush metadata."""
    if LAST_FLUSH_FILE.exists():
        try:
            return json.loads(LAST_FLUSH_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_flush_state(state: dict) -> None:
    """Persist the last flush metadata."""
    LAST_FLUSH_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def append_to_daily_log(content: str, section: str = "Session") -> Path:
    """Append a structured entry to today's daily log."""
    today = now_local()
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    log_path = DAILY_DIR / f"{today.strftime('%Y-%m-%d')}.md"

    if not log_path.exists():
        log_path.write_text(f"# Daily Log: {today.strftime('%Y-%m-%d')}\n\n## Sessions\n\n", encoding="utf-8")

    entry = f"### {section} ({today.strftime('%H:%M')})\n\n{content.strip()}\n\n"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(entry)

    return log_path


def maybe_trigger_compilation(changed_log: Path | None) -> None:
    """Compile automatically once per evening when today's log changed."""
    if changed_log is None or not changed_log.exists():
        return

    now = now_local()
    if now.hour < COMPILE_AFTER_HOUR:
        return

    state = load_state()
    ingested = state.get("ingested", {})
    existing = ingested.get(changed_log.name)
    if existing and existing.get("hash") == file_hash(changed_log):
        return

    cmd = ["uv", "run", "--directory", str(ROOT_DIR), "python", str(SCRIPTS_DIR / "compile.py")]
    with (SCRIPTS_DIR / "compile.log").open("a", encoding="utf-8") as log_handle:
        subprocess.Popen(
            cmd,
            cwd=ROOT_DIR,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def build_prompt(transcript: str) -> str:
    """Build the summarization prompt for the flush agent."""
    return f"""Review the transcript delta below and return a concise daily-log entry.

Rules:
- Return plain markdown only.
- Use these sections when relevant: Context, Key Exchanges, Decisions Made, Lessons Learned, Action Items.
- Skip trivial back-and-forth, routine tool output, and obvious filler.
- If nothing should be saved, respond exactly: FLUSH_OK

Transcript Delta:

{transcript}
"""


def main() -> int:
    if len(sys.argv) < 3:
        logging.error("Usage: %s <transcript_file> <session_id> [reason]", sys.argv[0])
        return 1

    transcript_path = Path(sys.argv[1])
    session_id = sys.argv[2]
    reason = sys.argv[3] if len(sys.argv) > 3 else "session.idle"

    if not transcript_path.exists():
        logging.error("Transcript file missing: %s", transcript_path)
        return 1

    transcript = transcript_path.read_text(encoding="utf-8").strip()
    if not transcript:
        transcript_path.unlink(missing_ok=True)
        return 0

    prior = load_flush_state()
    if prior.get("session_id") == session_id and prior.get("transcript_hash") == file_hash(transcript_path):
        logging.info("Skipping duplicate flush for %s", session_id)
        transcript_path.unlink(missing_ok=True)
        return 0

    logging.info("Running flush for %s (%s)", session_id, reason)

    try:
        result = run_opencode(
            build_prompt(transcript),
            agent="knowledge-flush",
            title=f"Memory flush {session_id}",
        )
    except Exception as exc:
        logging.error("Flush failed for %s: %s", session_id, exc)
        transcript_path.unlink(missing_ok=True)
        return 1

    changed_log: Path | None = None
    if result.text and result.text.strip() != "FLUSH_OK":
        changed_log = append_to_daily_log(result.text)
        logging.info("Appended memory entry to %s", changed_log.name)
    else:
        logging.info("Flush returned FLUSH_OK for %s", session_id)

    save_flush_state(
        {
            "session_id": session_id,
            "reason": reason,
            "flushed_at": now_iso(),
            "transcript_hash": file_hash(transcript_path),
            "cost_usd": result.cost,
        }
    )

    transcript_path.unlink(missing_ok=True)
    maybe_trigger_compilation(changed_log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
