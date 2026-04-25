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


def _parse_llm_json(text: str, valid_keys: set) -> dict | None:
    """Extract and validate a JSON object from LLM response text."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    tags = json.loads(text[start:end + 1])
    return {k: v for k, v in tags.items() if k in valid_keys and isinstance(v, str)}


def llm_tag(title: str, abstract: str, config: dict, max_retries: int = 2) -> dict | None:
    """Call LLM to tag a paper. Retries on empty/failed responses."""
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
