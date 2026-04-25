#!/usr/bin/env python3
"""CLI tool to manage the paper collection.

Usage:
    python scripts/manage.py add <arxiv_id_or_url> [--category CAT] [--tag key=value ...]
    python scripts/manage.py remove <arxiv_id_or_slug>
    python scripts/manage.py list [--category CAT]
    python scripts/manage.py retag [arxiv_id_or_slug]     # re-tag with LLM
    python scripts/manage.py fetch
"""

import argparse
import json
import re
import sys
from pathlib import Path

import arxiv
import yaml

from llm_tagger import llm_tag, merge_tags

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
PAPERS_PATH = ROOT / "docs" / "data" / "papers.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_papers() -> list[dict]:
    if PAPERS_PATH.exists():
        with open(PAPERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("papers", [])
    return []


def save_papers(papers: list[dict]):
    PAPERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PAPERS_PATH, "w", encoding="utf-8") as f:
        json.dump({"papers": papers}, f, indent=2, ensure_ascii=False)


def slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:80]


def parse_arxiv_id(input_str: str) -> str:
    """Extract arxiv ID from a URL or plain ID string."""
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", input_str)
    if m:
        return m.group(1)
    print(f"Error: cannot parse arxiv ID from '{input_str}'", file=sys.stderr)
    sys.exit(1)


def extract_github_url(text: str) -> str:
    m = re.search(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", text or "")
    if not m:
        return ""
    return m.group(0).rstrip(".")


def auto_tag(title: str, abstract: str, config: dict) -> dict:
    tags = {}
    auto_rules = config.get("auto_tags", {})
    combined = f"{title} {abstract}".lower()
    for facet_key, value_keywords in auto_rules.items():
        matched = None
        default = None
        for value, keywords in value_keywords.items():
            if not keywords:
                default = value
                continue
            for kw in keywords:
                if kw.lower() in combined:
                    matched = value
                    break
            if matched:
                break
        tags[facet_key] = matched or default or ""
    for facet in config.get("facets", []):
        if facet["key"] not in tags:
            tags[facet["key"]] = ""
    return tags


def cmd_add(args):
    """Add a paper by arxiv ID or URL."""
    config = load_config()
    arxiv_id = parse_arxiv_id(args.identifier)
    papers = load_papers()

    for p in papers:
        if arxiv_id in p.get("link", "") or arxiv_id in p.get("id", ""):
            print(f"Paper {arxiv_id} already exists: {p['title']}")
            return

    client = arxiv.Client()
    search = arxiv.Search(id_list=[arxiv_id])
    results = list(client.results(search))
    if not results:
        print(f"Error: paper {arxiv_id} not found on arxiv", file=sys.stderr)
        sys.exit(1)

    result = results[0]
    comment = result.comment or ""
    abstract = result.summary or ""
    code_url = extract_github_url(abstract) or extract_github_url(comment)

    venue = ""
    venue_match = re.search(
        r"(?:accepted|published|appear)\s+(?:at|in|by)\s+([A-Z][A-Za-z0-9\s&-]+\d{2,4})",
        comment,
        re.IGNORECASE,
    )
    if venue_match:
        venue = venue_match.group(1).strip()

    tags = auto_tag(result.title, abstract, config)
    llm_tags_result = llm_tag(result.title, abstract, config)
    tags = merge_tags(tags, llm_tags_result)

    # Apply CLI overrides
    if args.category:
        tags["category"] = args.category
    if args.tag:
        for t in args.tag:
            if "=" in t:
                k, v = t.split("=", 1)
                tags[k] = v

    paper = {
        "id": slugify(result.title),
        "title": result.title.strip(),
        "abstract": abstract.strip(),
        "venue": venue,
        "year": result.published.year,
        "date": result.published.strftime("%Y-%m-%d"),
        "link": f"https://arxiv.org/abs/{arxiv_id}",
        "code": code_url,
        "notes": "",
        "authors": ", ".join(a.name for a in result.authors[:5])
                   + (" et al." if len(result.authors) > 5 else ""),
        "tags": tags,
    }

    papers.append(paper)
    save_papers(papers)
    print(f"Added: {paper['title']}  ({paper['link']})")


def cmd_remove(args):
    """Remove a paper by arxiv ID or slug."""
    papers = load_papers()
    identifier = args.identifier.lower()
    remaining = []
    removed = False
    for p in papers:
        if identifier in p.get("id", "") or identifier in p.get("link", ""):
            print(f"Removed: {p['title']}")
            removed = True
        else:
            remaining.append(p)
    if not removed:
        print(f"Paper not found: {args.identifier}")
        return
    save_papers(remaining)
    print(f"Remaining papers: {len(remaining)}")


def cmd_list(args):
    """List all papers, optionally filtered."""
    papers = load_papers()
    if args.category:
        papers = [p for p in papers if p.get("tags", {}).get("category") == args.category]

    if not papers:
        print("No papers found.")
        return

    for p in sorted(papers, key=lambda x: x.get("date", ""), reverse=True):
        tags_str = ", ".join(f"{k}={v}" for k, v in p.get("tags", {}).items() if v)
        code_mark = " [code]" if p.get("code") else ""
        print(f"  {p['date']}  {p['title']}{code_mark}")
        print(f"           {p['link']}  [{tags_str}]")

    print(f"\nTotal: {len(papers)} papers")


def cmd_retag(args):
    """Re-tag all papers (or specific ones) using LLM."""
    config = load_config()
    papers = load_papers()
    if not papers:
        print("No papers to re-tag.")
        return

    target = args.identifier.lower() if args.identifier else None
    count = 0

    for p in papers:
        if target and target not in p.get("id", "") and target not in p.get("link", ""):
            continue

        title = p.get("title", "")
        # We need the abstract; fetch from arxiv if not stored
        arxiv_id_match = re.search(r"(\d{4}\.\d{4,5})", p.get("link", ""))
        abstract = ""
        if arxiv_id_match:
            try:
                client = arxiv.Client()
                results = list(client.results(arxiv.Search(id_list=[arxiv_id_match.group(1)])))
                if results:
                    abstract = results[0].summary or ""
            except Exception:
                pass

        llm_result = llm_tag(title, abstract, config)
        if llm_result:
            old_tags = p.get("tags", {})
            p["tags"] = merge_tags(old_tags, llm_result)
            count += 1
            print(f"  Re-tagged: {title[:60]}  -> {p['tags']}")

    save_papers(papers)
    print(f"\nRe-tagged {count} papers.")


def cmd_fetch(_args):
    """Trigger automatic fetch from arxiv."""
    from fetch_papers import main as fetch_main
    fetch_main()


def main():
    parser = argparse.ArgumentParser(description="Manage awesome-papers collection")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add a paper by arxiv ID or URL")
    p_add.add_argument("identifier", help="arxiv ID (e.g. 2312.00752) or URL")
    p_add.add_argument("--category", help="Override category tag")
    p_add.add_argument("--tag", action="append", help="Extra tag as key=value")

    p_rm = sub.add_parser("remove", help="Remove a paper")
    p_rm.add_argument("identifier", help="arxiv ID or slug")

    p_ls = sub.add_parser("list", help="List papers")
    p_ls.add_argument("--category", help="Filter by category")

    p_retag = sub.add_parser("retag", help="Re-tag papers using LLM")
    p_retag.add_argument("identifier", nargs="?", default=None,
                         help="Optional: specific arxiv ID or slug to re-tag (default: all)")

    sub.add_parser("fetch", help="Run automatic arxiv fetch")

    args = parser.parse_args()
    cmds = {"add": cmd_add, "remove": cmd_remove, "list": cmd_list,
            "retag": cmd_retag, "fetch": cmd_fetch}
    cmds[args.command](args)


if __name__ == "__main__":
    main()
