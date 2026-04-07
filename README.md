# LLM Wiki for OpenCode

**OpenCode conversations compile themselves into a persistent markdown wiki.**

This project adapts Andrej Karpathy's [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) to OpenCode. Instead of treating each conversation as disposable chat history, the repo captures meaningful session deltas into daily logs, then compiles those logs into a structured wiki with concept pages, connection pages, and filed answers.

## How It Works

```text
OpenCode session
  -> .opencode/plugins/llm-wiki.js captures new transcript deltas
  -> scripts/flush.py summarizes them into daily/YYYY-MM-DD.md
  -> scripts/compile.py compiles daily logs into knowledge/*
  -> scripts/query.py answers from the wiki
  -> scripts/lint.py health-checks the wiki
```

The architecture mirrors the Claude-oriented reference repo, but swaps Claude hooks for OpenCode plugins and uses `opencode run` for the LLM work.

## Setup

1. Install Python dependencies and create the runtime environment:

   ```bash
   uv sync
   ```

2. Install the local OpenCode plugin dependency:

   ```bash
   npm install --prefix .opencode
   ```

3. Open this repo in OpenCode.

Project config lives in [opencode.json](/Users/rsoutar/Projects/rsoutar/llm-wiki/opencode.json) and the compiler schema lives in [AGENTS.md](/Users/rsoutar/Projects/rsoutar/llm-wiki/AGENTS.md).

## Commands

```bash
uv run python scripts/compile.py
uv run python scripts/compile.py --all
uv run python scripts/compile.py --file daily/2026-04-07.md
uv run python scripts/query.py "What patterns do I keep using for auth?"
uv run python scripts/query.py "How do I tend to structure background jobs?" --file-back
uv run python scripts/lint.py
uv run python scripts/lint.py --structural-only
```

## Notes

- Automatic capture happens through the local OpenCode plugin in `.opencode/plugins/`.
- The plugin injects the current wiki index and recent log context back into future sessions.
- After 6 PM local time, a successful memory flush can automatically trigger compilation if the daily log changed.
- Internal maintenance runs set `OPENCODE_MEMORY_INTERNAL=1` so they do not recursively trigger the capture plugin.
