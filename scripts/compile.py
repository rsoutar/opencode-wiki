"""Compile daily logs into wiki articles using OpenCode."""

from __future__ import annotations

import argparse
from pathlib import Path

from config import CONNECTIONS_DIR, DAILY_DIR, INDEX_FILE, KNOWLEDGE_DIR, LOG_FILE, ROOT_DIR, now_iso
from opencode_runner import run_opencode
from utils import file_hash, list_raw_files, list_wiki_articles, load_state, save_state


def ensure_scaffold() -> None:
    """Ensure the wiki scaffold exists before compilation."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    CONNECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    (KNOWLEDGE_DIR / "concepts").mkdir(parents=True, exist_ok=True)
    (KNOWLEDGE_DIR / "qa").mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text(
            "# Knowledge Base Index\n\n| Article | Summary | Compiled From | Updated |\n|---------|---------|---------------|---------|\n",
            encoding="utf-8",
        )
    if not LOG_FILE.exists():
        LOG_FILE.write_text("# Build Log\n", encoding="utf-8")


def build_compile_prompt(log_path: Path) -> str:
    """Prompt for compiling one daily log."""
    timestamp = now_iso()
    return f"""Compile `daily/{log_path.name}` into the wiki defined by AGENTS.md.

Required workflow:
1. Read `knowledge/index.md` first.
2. Read `daily/{log_path.name}` in full.
3. Read any relevant existing wiki pages before editing.
4. Create or update `knowledge/concepts/*.md` as needed.
5. Create `knowledge/connections/*.md` only when the log reveals a real cross-cutting insight.
6. Update `knowledge/index.md`.
7. Append an entry to `knowledge/log.md` using timestamp `{timestamp}`.

Quality bar:
- Prefer updates over duplicate pages.
- Every article needs YAML frontmatter.
- Use Obsidian wikilinks without `.md`.
- Keep the writing factual and reusable.

At the end, print a short summary in this exact style:
CREATED: [[concepts/example]], [[connections/example]]
UPDATED: [[concepts/example]]
"""


def compile_daily_log(log_path: Path, state: dict) -> float:
    """Compile one daily log and update state."""
    result = run_opencode(
        build_compile_prompt(log_path),
        agent="knowledge-compiler",
        title=f"Compile {log_path.name}",
    )
    print(result.text or "(no textual summary)")

    state.setdefault("ingested", {})[log_path.name] = {
        "hash": file_hash(log_path),
        "compiled_at": now_iso(),
        "cost_usd": result.cost,
    }
    state["total_cost"] = state.get("total_cost", 0.0) + result.cost
    save_state(state)
    return result.cost


def resolve_targets(args: argparse.Namespace, state: dict) -> list[Path]:
    """Resolve which daily logs should be compiled."""
    if args.file:
        target = Path(args.file)
        if not target.is_absolute():
            target = DAILY_DIR / target.name
        if not target.exists():
            target = ROOT_DIR / args.file
        if not target.exists():
            raise FileNotFoundError(args.file)
        return [target]

    all_logs = list_raw_files()
    if args.all:
        return all_logs

    targets = []
    for log_path in all_logs:
        previous = state.get("ingested", {}).get(log_path.name, {})
        if previous.get("hash") != file_hash(log_path):
            targets.append(log_path)
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile daily logs into wiki articles")
    parser.add_argument("--all", action="store_true", help="Recompile all daily logs")
    parser.add_argument("--file", type=str, help="Compile a specific daily log")
    parser.add_argument("--dry-run", action="store_true", help="Show which files would be compiled")
    args = parser.parse_args()

    ensure_scaffold()
    state = load_state()

    try:
        targets = resolve_targets(args, state)
    except FileNotFoundError as exc:
        print(f"Error: {exc} not found")
        return 1

    if not targets:
        print("Nothing to compile - all daily logs are up to date.")
        return 0

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Files to compile ({len(targets)}):")
    for target in targets:
        print(f"  - {target.name}")

    if args.dry_run:
        return 0

    total_cost = 0.0
    for index, target in enumerate(targets, start=1):
        print(f"\n[{index}/{len(targets)}] Compiling {target.name}...")
        total_cost += compile_daily_log(target, state)

    print(f"\nCompilation complete. Total cost: ${total_cost:.4f}")
    print(f"Knowledge base: {len(list_wiki_articles())} article(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
