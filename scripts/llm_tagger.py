#!/usr/bin/env python3
"""Use DeepSeek (or any OpenAI-compatible API) to auto-tag papers."""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

_client = None


def _get_client(config: dict):
    global _client
    if _client is not None:
        return _client

    llm_cfg = config.get("llm", {})
    if not llm_cfg.get("enabled"):
        return None

    api_key = os.environ.get(llm_cfg.get("api_key_env", "DEEPSEEK_API_KEY"), "")
    if not api_key:
        print(f"Warning: env var {llm_cfg.get('api_key_env')} not set, skipping LLM tagging",
              file=sys.stderr)
        return None

    _client = OpenAI(
        api_key=api_key,
        base_url=llm_cfg.get("base_url", "https://api.deepseek.com"),
    )
    return _client


def _strip_markdown_fence(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0].strip()
    return text


def _parse_llm_json(text: str, valid_keys: set) -> dict | None:
    """Extract and validate a JSON object from LLM response text."""
    text = _strip_markdown_fence(text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    tags = json.loads(text[start:end + 1])
    return {k: v for k, v in tags.items() if k in valid_keys and isinstance(v, str)}


def _parse_llm_json_array(text: str) -> list | None:
    """Extract a JSON array from LLM response text."""
    text = _strip_markdown_fence(text)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return None
    return json.loads(text[start:end + 1])


# ---------------------------------------------------------------------------
# Single-paper tagging (legacy, kept for manage.py retag)
# ---------------------------------------------------------------------------

def _build_prompt(title: str, abstract: str, config: dict) -> str:
    facets = config.get("facets", [])
    facet_desc = []
    for f in facets:
        values = f.get("values", [])
        facet_desc.append(f'- "{f["key"]}" (label: {f["label"]}): choose from {values}')

    return f"""You are a research paper classifier. Given a paper's title and abstract, assign tags for each dimension below.

Dimensions:
{chr(10).join(facet_desc)}

Rules:
- For each dimension, pick the SINGLE most appropriate value from the provided list.
- If none of the values fit well, return an empty string "".
- Return ONLY a JSON object with dimension keys and string values. No explanation.

Paper title: {title}

Abstract: {abstract}

Output JSON:"""


def llm_tag(title: str, abstract: str, config: dict, max_retries: int = 2) -> dict | None:
    """Call LLM to tag a single paper. Retries on empty/failed responses."""
    client = _get_client(config)
    if client is None:
        return None

    llm_cfg = config.get("llm", {})
    model = llm_cfg.get("model", "deepseek-chat")
    prompt = _build_prompt(title, abstract, config)
    valid_keys = {f["key"] for f in config.get("facets", [])}

    for attempt in range(max_retries + 1):
        try:
            temp = 0 if attempt == 0 else 0.3
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a research paper classifier. Always respond with a valid JSON object only, no explanation."},
                    {"role": "user", "content": prompt},
                ],
                temperature=temp,
                max_tokens=300,
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                continue
            result = _parse_llm_json(text, valid_keys)
            if result:
                return result
        except Exception as e:
            if attempt == max_retries:
                print(f"Warning: LLM tagging failed for '{title[:50]}...': {e}", file=sys.stderr)
    return None


def merge_tags(rule_tags: dict, llm_tags: dict | None) -> dict:
    """Merge rule-based tags with LLM tags. LLM fills in blanks left by rules."""
    if not llm_tags:
        return rule_tags
    merged = dict(rule_tags)
    for k, v in llm_tags.items():
        if not merged.get(k) and v:
            merged[k] = v
    return merged


# ---------------------------------------------------------------------------
# Batch classify: filter + full tagging in one LLM call
# ---------------------------------------------------------------------------

def _build_batch_prompt(papers: list[dict], facets: list[dict]) -> str:
    """Build prompt for batch classification of multiple papers."""
    dim_lines = []
    topic_facet = None
    for f in facets:
        vals = f.get("values", [])
        if f["key"] == "topic":
            topic_facet = f
            dim_lines.append(
                f'- "{f["key"]}": choose from {vals}\n'
                f'  If the paper does NOT belong to any of these topics, set to null.'
            )
        else:
            dim_lines.append(f'- "{f["key"]}": choose from {vals}')

    paper_lines = []
    for i, p in enumerate(papers, 1):
        title = p.get("title", "")
        abstract = (p.get("abstract", "") or "")[:500]
        paper_lines.append(f"[{i}] Title: {title}\nAbstract: {abstract}")

    return f"""Classify each paper into ALL dimensions at once.

Dimensions:
{chr(10).join(dim_lines)}

Rules:
- "topic" is the FILTER: only assign a topic if the paper clearly belongs to that research area. Otherwise set topic to null.
- If topic is null, set ALL other dimensions to null too, and return null for that paper.
- For relevant papers, pick the SINGLE best value for each dimension.
- Return a JSON array with exactly {len(papers)} elements. Each element is either an object with all dimension keys, or null (if topic is null).

Papers:
{chr(10).join(paper_lines)}

Output JSON array:"""


def _classify_single(paper: dict, facets: list[dict], config: dict) -> dict | None:
    """Fallback: classify a single paper when batch parsing fails."""
    result = llm_tag(paper.get("title", ""), paper.get("abstract", ""), config)
    if not result:
        return None
    topic_val = result.get("topic", "")
    if not topic_val:
        return None
    topic_values = set()
    for f in facets:
        if f["key"] == "topic":
            topic_values = set(f.get("values", []))
            break
    if topic_val not in topic_values:
        return None
    return result


def llm_classify_batch(
    papers: list[dict],
    facets: list[dict],
    config: dict,
    batch_size: int = 10,
) -> list[dict | None]:
    """
    Batch classify papers. Returns a list of tag dicts or None (discard).
    topic=null means the paper is not relevant and should be discarded.
    """
    client = _get_client(config)
    if client is None:
        return [None] * len(papers)

    llm_cfg = config.get("llm", {})
    model = llm_cfg.get("model", "deepseek-chat")
    valid_keys = {f["key"] for f in facets}
    topic_values = set()
    for f in facets:
        if f["key"] == "topic":
            topic_values = set(f.get("values", []))
            break

    all_results: list[dict | None] = []
    total_batches = (len(papers) + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(papers))
        batch = papers[start:end]
        batch_num = batch_idx + 1

        prompt = _build_batch_prompt(batch, facets)
        parsed = None

        for attempt in range(3):
            try:
                temp = 0 if attempt == 0 else 0.3
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a research paper classifier. Always respond with a valid JSON array only, no explanation."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temp,
                    max_tokens=200 * len(batch),
                )
                text = (resp.choices[0].message.content or "").strip()
                if not text:
                    continue
                arr = _parse_llm_json_array(text)
                if arr is not None and len(arr) == len(batch):
                    parsed = arr
                    break
            except Exception as e:
                if attempt == 2:
                    print(f"Warning: batch {batch_num}/{total_batches} LLM call failed: {e}",
                          file=sys.stderr)

        if parsed is not None:
            for item in parsed:
                if item is None or not isinstance(item, dict):
                    all_results.append(None)
                    continue
                topic = item.get("topic")
                if topic is None or topic not in topic_values:
                    all_results.append(None)
                    continue
                tags = {k: v for k, v in item.items()
                        if k in valid_keys and isinstance(v, str)}
                tags["topic"] = topic
                all_results.append(tags)
        else:
            print(f"  Batch {batch_num}/{total_batches} parse failed, falling back to single-paper mode",
                  file=sys.stderr)
            for p in batch:
                all_results.append(_classify_single(p, facets, config))

        print(f"  Batch {batch_num}/{total_batches} done", file=sys.stderr)

    return all_results
