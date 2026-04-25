#!/usr/bin/env python3
"""Fetch new papers from arxiv based on config.yaml keywords and append to papers.json."""

import json
import re
import sys
from datetime import datetime, timedelta
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


def load_papers():
    if PAPERS_PATH.exists():
        with open(PAPERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("papers", [])
    return []


def save_papers(papers):
    PAPERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PAPERS_PATH, "w", encoding="utf-8") as f:
        json.dump({"papers": papers}, f, indent=2, ensure_ascii=False)


def slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:80]


def extract_github_url(text: str) -> str:
    """Try to find a GitHub repo URL in the abstract or comments."""
    m = re.search(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", text or "")
    if not m:
        return ""
    url = m.group(0).rstrip(".")
    return url


def auto_tag(title: str, abstract: str, config: dict) -> dict:
    """Apply rule-based tagging from config.auto_tags."""
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

    # Populate any facet keys from config that aren't covered by auto_tags
    for facet in config.get("facets", []):
        if facet["key"] not in tags:
            tags[facet["key"]] = ""

    return tags


def build_query(config: dict) -> str:
    keywords = config.get("keywords", [])
    if not keywords:
        print("Error: no keywords defined in config.yaml", file=sys.stderr)
        sys.exit(1)
    parts = [f'all:"{kw}"' for kw in keywords]
    return " OR ".join(parts)


def fetch(config: dict) -> list[dict]:
    """Search arxiv and return list of new paper dicts."""
    query = build_query(config)
    max_results = config.get("max_results_per_fetch", 100)

    client = arxiv.Client()
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    existing_ids = {p["id"] for p in load_papers()}
    new_papers = []

    for result in client.results(search):
        paper_id = slugify(result.title)
        arxiv_id = result.entry_id.split("/")[-1]

        if paper_id in existing_ids or arxiv_id in existing_ids:
            continue

        comment = result.comment or ""
        abstract = result.summary or ""
        code_url = extract_github_url(abstract) or extract_github_url(comment)

        venue = ""
        # Try to extract venue from comments like "Accepted at NeurIPS 2024"
        venue_match = re.search(
            r"(?:accepted|published|appear)\s+(?:at|in|by)\s+([A-Z][A-Za-z0-9\s&-]+\d{2,4})",
            comment,
            re.IGNORECASE,
        )
        if venue_match:
            venue = venue_match.group(1).strip()

        tags = auto_tag(result.title, abstract, config)
        llm_tags = llm_tag(result.title, abstract, config)
        tags = merge_tags(tags, llm_tags)

        paper = {
            "id": paper_id,
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
        new_papers.append(paper)
        existing_ids.add(paper_id)

    return new_papers


def main():
    config = load_config()
    print(f"Searching arxiv with keywords: {config.get('keywords', [])}")

    new_papers = fetch(config)
    if not new_papers:
        print("No new papers found.")
        return

    papers = load_papers()
    papers.extend(new_papers)
    save_papers(papers)
    print(f"Added {len(new_papers)} new papers. Total: {len(papers)}")


if __name__ == "__main__":
    main()
