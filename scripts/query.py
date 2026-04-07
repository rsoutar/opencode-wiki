"""Query the compiled wiki via OpenCode."""

from __future__ import annotations

import argparse

from config import LOG_FILE, QA_DIR, now_iso
from opencode_runner import run_opencode
from utils import load_state, save_state, slugify


def build_query_prompt(question: str, file_back: bool) -> str:
    """Build the wiki query prompt."""
    if not file_back:
        return f"""Answer this question from the wiki:

Question: {question}

Workflow:
- Read `knowledge/index.md` first.
- Read only the most relevant wiki pages.
- Cite wiki pages with `[[wikilinks]]`.
- If the wiki does not contain the answer, say so plainly.
"""

    qa_slug = slugify(question) or "query-answer"
    timestamp = now_iso()
    return f"""Answer this question from the wiki and file the result back into the knowledge base.

Question: {question}

Required workflow:
- Read `knowledge/index.md` first.
- Read only the most relevant wiki pages.
- Answer with `[[wikilinks]]`.
- Create `knowledge/qa/{qa_slug}.md` using the Q&A format from AGENTS.md.
- Update `knowledge/index.md`.
- Append an entry to `knowledge/log.md` with timestamp `{timestamp}`.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Query the wiki")
    parser.add_argument("question", help="Question to ask the wiki")
    parser.add_argument("--file-back", action="store_true", help="Store the answer as a Q&A page")
    args = parser.parse_args()

    result = run_opencode(
        build_query_prompt(args.question, args.file_back),
        agent="knowledge-query",
        title=f"Query wiki: {args.question[:60]}",
    )

    print(result.text)

    state = load_state()
    state["query_count"] = state.get("query_count", 0) + 1
    state["total_cost"] = state.get("total_cost", 0.0) + result.cost
    if args.file_back:
        state["last_filed_query"] = {"question": args.question, "filed_at": now_iso()}
    save_state(state)

    if args.file_back:
        print(f"\nFiled answer back into {QA_DIR} and logged the operation in {LOG_FILE}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
