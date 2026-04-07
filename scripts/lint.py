"""Lint the wiki for structural and semantic health."""

from __future__ import annotations

import argparse

from config import KNOWLEDGE_DIR, REPORTS_DIR, now_iso, today_iso
from opencode_runner import run_opencode
from utils import (
    count_inbound_links,
    extract_wikilinks,
    file_hash,
    get_article_word_count,
    list_raw_files,
    list_wiki_articles,
    load_state,
    save_state,
    wiki_article_exists,
)


def check_broken_links() -> list[dict]:
    issues = []
    for article in list_wiki_articles():
        rel = article.relative_to(KNOWLEDGE_DIR).as_posix()
        for link in extract_wikilinks(article.read_text(encoding="utf-8")):
            if link.startswith("daily/"):
                continue
            if not wiki_article_exists(link):
                issues.append(
                    {
                        "severity": "error",
                        "check": "broken_link",
                        "file": rel,
                        "detail": f"Broken link: [[{link}]]",
                    }
                )
    return issues


def check_orphan_pages() -> list[dict]:
    issues = []
    for article in list_wiki_articles():
        rel = article.relative_to(KNOWLEDGE_DIR).as_posix()
        target = rel.removesuffix(".md")
        if count_inbound_links(target) == 0:
            issues.append(
                {
                    "severity": "warning",
                    "check": "orphan_page",
                    "file": rel,
                    "detail": f"No other page links to [[{target}]]",
                }
            )
    return issues


def check_orphan_sources() -> list[dict]:
    state = load_state()
    issues = []
    for log_path in list_raw_files():
        if log_path.name not in state.get("ingested", {}):
            issues.append(
                {
                    "severity": "warning",
                    "check": "orphan_source",
                    "file": f"daily/{log_path.name}",
                    "detail": "Daily log has not been compiled yet",
                }
            )
    return issues


def check_stale_articles() -> list[dict]:
    state = load_state()
    issues = []
    for log_path in list_raw_files():
        stored = state.get("ingested", {}).get(log_path.name)
        if stored and stored.get("hash") != file_hash(log_path):
            issues.append(
                {
                    "severity": "warning",
                    "check": "stale_article",
                    "file": f"daily/{log_path.name}",
                    "detail": "Daily log changed after its last compilation",
                }
            )
    return issues


def check_missing_backlinks() -> list[dict]:
    issues = []
    for article in list_wiki_articles():
        rel = article.relative_to(KNOWLEDGE_DIR).as_posix()
        source_link = rel.removesuffix(".md")
        content = article.read_text(encoding="utf-8")
        for link in extract_wikilinks(content):
            if link.startswith("daily/"):
                continue
            target = KNOWLEDGE_DIR / f"{link}.md"
            if target.exists() and f"[[{source_link}]]" not in target.read_text(encoding="utf-8"):
                issues.append(
                    {
                        "severity": "suggestion",
                        "check": "missing_backlink",
                        "file": rel,
                        "detail": f"[[{source_link}]] links to [[{link}]] but not vice versa",
                    }
                )
    return issues


def check_sparse_articles() -> list[dict]:
    issues = []
    for article in list_wiki_articles():
        word_count = get_article_word_count(article)
        if word_count < 200:
            issues.append(
                {
                    "severity": "suggestion",
                    "check": "sparse_article",
                    "file": article.relative_to(KNOWLEDGE_DIR).as_posix(),
                    "detail": f"Only {word_count} words",
                }
            )
    return issues


def check_contradictions() -> list[dict]:
    result = run_opencode(
        """Review the wiki for contradictions, stale guidance, or inconsistent recommendations.

Read `knowledge/index.md` first and then the most suspicious pages.

Return only lines in one of these formats:
CONTRADICTION: [file1] vs [file2] - description
INCONSISTENCY: [file] - description

If you find nothing, return exactly: NO_ISSUES
""",
        agent="knowledge-linter",
        title="Lint wiki contradictions",
    )

    issues = []
    for line in result.text.splitlines():
        line = line.strip()
        if line.startswith("CONTRADICTION:") or line.startswith("INCONSISTENCY:"):
            issues.append(
                {
                    "severity": "warning",
                    "check": "contradiction",
                    "file": "(cross-article)",
                    "detail": line,
                }
            )
    return issues


def generate_report(issues: list[dict]) -> str:
    errors = [issue for issue in issues if issue["severity"] == "error"]
    warnings = [issue for issue in issues if issue["severity"] == "warning"]
    suggestions = [issue for issue in issues if issue["severity"] == "suggestion"]

    lines = [
        f"# Lint Report - {today_iso()}",
        "",
        f"**Total issues:** {len(issues)}",
        f"- Errors: {len(errors)}",
        f"- Warnings: {len(warnings)}",
        f"- Suggestions: {len(suggestions)}",
        "",
    ]

    for heading, group in (("Errors", errors), ("Warnings", warnings), ("Suggestions", suggestions)):
        if not group:
            continue
        lines.append(f"## {heading}")
        lines.append("")
        for issue in group:
            lines.append(f"- `{issue['file']}` - {issue['detail']}")
        lines.append("")

    if not issues:
        lines.append("All checks passed.")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint the wiki")
    parser.add_argument("--structural-only", action="store_true", help="Skip the contradiction check")
    args = parser.parse_args()

    print("Running lint checks...")
    issues: list[dict] = []

    for name, fn in (
        ("Broken links", check_broken_links),
        ("Orphan pages", check_orphan_pages),
        ("Orphan sources", check_orphan_sources),
        ("Stale articles", check_stale_articles),
        ("Missing backlinks", check_missing_backlinks),
        ("Sparse articles", check_sparse_articles),
    ):
        found = fn()
        issues.extend(found)
        print(f"  {name}: {len(found)}")

    if not args.structural_only:
        found = check_contradictions()
        issues.extend(found)
        print(f"  Contradictions: {len(found)}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"lint-{today_iso()}.md"
    report_path.write_text(generate_report(issues), encoding="utf-8")
    print(f"\nReport saved to: {report_path}")

    state = load_state()
    state["last_lint"] = now_iso()
    save_state(state)

    errors = sum(1 for issue in issues if issue["severity"] == "error")
    warnings = sum(1 for issue in issues if issue["severity"] == "warning")
    suggestions = sum(1 for issue in issues if issue["severity"] == "suggestion")
    print(f"Results: {errors} errors, {warnings} warnings, {suggestions} suggestions")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
