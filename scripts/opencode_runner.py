"""Helpers for driving OpenCode in headless mode."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

from config import INTERNAL_ENV, ROOT_DIR


@dataclass
class OpenCodeResult:
    """Structured result from an OpenCode headless run."""

    text: str
    session_id: str | None
    cost: float
    raw_stdout: str
    raw_stderr: str


def run_opencode(
    prompt: str,
    *,
    agent: str | None = None,
    model: str | None = None,
    title: str | None = None,
) -> OpenCodeResult:
    """Run `opencode run` and collect text output from JSON events."""
    cmd = ["opencode", "run", "--format", "json"]

    if agent:
        cmd.extend(["--agent", agent])
    if model:
        cmd.extend(["--model", model])
    if title:
        cmd.extend(["--title", title])

    cmd.append(prompt)

    env = os.environ.copy()
    env[INTERNAL_ENV] = "1"

    completed = subprocess.run(
        cmd,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    text_chunks: list[str] = []
    session_id: str | None = None
    total_cost = 0.0

    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            text_chunks.append(line)
            continue

        session_id = session_id or event.get("sessionID")
        event_type = event.get("type")
        part = event.get("part", {})

        if event_type == "text" and part.get("text"):
            text_chunks.append(part["text"])
        elif event_type == "step_finish":
            total_cost += float(part.get("cost", 0.0) or 0.0)

    text = "".join(text_chunks).strip()

    if completed.returncode != 0 and not text:
        stderr = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"OpenCode run failed ({completed.returncode}): {stderr}")

    return OpenCodeResult(
        text=text,
        session_id=session_id,
        cost=total_cost,
        raw_stdout=completed.stdout,
        raw_stderr=completed.stderr,
    )
