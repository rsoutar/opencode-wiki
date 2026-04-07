"""Utility helpers for the LLM wiki scripts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from config import (
    CONCEPTS_DIR,
    CONNECTIONS_DIR,
    DAILY_DIR,
    INDEX_FILE,
    KNOWLEDGE_DIR,
    QA_DIR,
    STATE_FILE,
)


def load_state() -> dict:
    """Load compile/query state."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"ingested": {}, "query_count": 0, "last_lint": None, "total_cost": 0.0}


def save_state(state: dict) -> None:
    """Persist compile/query state."""
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def file_hash(path: Path) -> str:
    """SHA-256 hash of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def slugify(text: str) -> str:
    """Convert text to a filesystem-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def extract_wikilinks(content: str) -> list[str]:
    """Extract Obsidian-style wikilinks."""
    return re.findall(r"\[\[([^\]]+)\]\]", content)


def wiki_article_exists(link: str) -> bool:
    """Return whether a wikilink target exists on disk."""
    return (KNOWLEDGE_DIR / f"{link}.md").exists()


def read_wiki_index() -> str:
    """Read or initialize the wiki index."""
    if INDEX_FILE.exists():
        return INDEX_FILE.read_text(encoding="utf-8")
    return "# Knowledge Base Index\n\n| Article | Summary | Compiled From | Updated |\n|---------|---------|---------------|---------|"


def list_wiki_articles() -> list[Path]:
    """List all wiki article files."""
    articles: list[Path] = []
    for subdir in (CONCEPTS_DIR, CONNECTIONS_DIR, QA_DIR):
        if subdir.exists():
            articles.extend(sorted(subdir.glob("*.md")))
    return articles


def list_raw_files() -> list[Path]:
    """List all daily log files."""
    if not DAILY_DIR.exists():
        return []
    return sorted(path for path in DAILY_DIR.glob("*.md") if path.is_file())


def read_all_wiki_content() -> str:
    """Read index and all wiki articles into a single string."""
    parts = [f"## INDEX\n\n{read_wiki_index()}"]
    for article in list_wiki_articles():
        rel = article.relative_to(KNOWLEDGE_DIR)
        parts.append(f"## {rel.as_posix()}\n\n{article.read_text(encoding='utf-8')}")
    return "\n\n---\n\n".join(parts)


def count_inbound_links(target: str, exclude_file: Path | None = None) -> int:
    """Count inbound wikilinks to a target."""
    count = 0
    for article in list_wiki_articles():
        if article == exclude_file:
            continue
        content = article.read_text(encoding="utf-8")
        if f"[[{target}]]" in content:
            count += 1
    return count


def get_article_word_count(path: Path) -> int:
    """Count article words, excluding YAML frontmatter."""
    content = path.read_text(encoding="utf-8")
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            content = content[end + 4 :]
    return len(content.split())
