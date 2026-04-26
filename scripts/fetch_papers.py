#!/usr/bin/env python3
"""Fetch papers by arxiv category, filter & tag with LLM, append to papers.json."""

import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import arxiv
import yaml

from llm_tagger import llm_classify_batch

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
    return m.group(0).rstrip(".")


def fetch_by_categories(config: dict) -> list[dict]:
    """Fetch recent papers from arxiv by category, deduplicated by arxiv ID."""
    categories = config.get("arxiv_categories", [])
    if not categories:
        print("Error: no arxiv_categories in config.yaml", file=sys.stderr)
        sys.exit(1)

    days = config.get("days_lookback", 3)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    client = arxiv.Client()
    seen_ids: dict[str, dict] = {}

    for cat in categories:
        search = arxiv.Search(
            query=f"cat:{cat}",
            max_results=None,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        cat_count = 0
        for result in client.results(search):
            pub = result.published if result.published.tzinfo else result.published.replace(tzinfo=timezone.utc)
            if pub < cutoff:
                break
            arxiv_id = result.entry_id.split("/")[-1].split("v")[0]
            if arxiv_id in seen_ids:
                continue

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

            paper = {
                "id": slugify(result.title),
                "arxiv_id": arxiv_id,
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
                "tags": {},
            }
            seen_ids[arxiv_id] = paper
            cat_count += 1

        print(f"  {cat}: {cat_count} papers")

    return list(seen_ids.values())


def main():
    config = load_config()
    facets = config.get("facets", [])
    categories = config.get("arxiv_categories", [])
    print(f"Fetching from arxiv categories: {categories}")

    raw = fetch_by_categories(config)
    print(f"Fetched {len(raw)} unique papers")

    existing = load_papers()
    existing_ids = set()
    for p in existing:
        existing_ids.add(p["id"])
        if "arxiv_id" in p:
            existing_ids.add(p["arxiv_id"])
        link = p.get("link", "")
        if "/abs/" in link:
            existing_ids.add(link.split("/abs/")[-1].split("v")[0])

    candidates = [p for p in raw
                  if p["id"] not in existing_ids and p["arxiv_id"] not in existing_ids]
    print(f"Candidates after dedup: {len(candidates)}")

    if not candidates:
        print("No new candidate papers to classify.")
        return

    print("Running LLM classification...")
    results = llm_classify_batch(candidates, facets, config)

    new_papers = []
    topic_counter: Counter = Counter()
    for paper, tags in zip(candidates, results):
        if tags is not None:
            paper["tags"] = tags
            topic_counter[tags.get("topic", "?")] += 1
            new_papers.append(paper)

    discarded = len(candidates) - len(new_papers)
    print(f"Results: {len(new_papers)} relevant, {discarded} discarded")
    for topic, count in topic_counter.most_common():
        print(f"  - {topic}: {count}")

    if not new_papers:
        print("No relevant papers found after LLM filtering.")
        return

    existing.extend(new_papers)
    save_papers(existing)
    print(f"Added {len(new_papers)} new papers. Total: {len(existing)}")


if __name__ == "__main__":
    main()
