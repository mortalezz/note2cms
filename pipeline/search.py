"""
Search index builder and query engine for note2cms.

Generates a static `search-index.json` for optional client-side search (`/posts/search/`)
and powers the `GET /search?q=...` API endpoint.
"""

import json
import re
from typing import Optional


def _strip_markdown(raw: str) -> str:
    """Convert raw Markdown with optional frontmatter into clean searchable text."""
    text = raw or ""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            text = parts[2]
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"!\[.*?\]\(.*?\)", " ", text)
    text = re.sub(r"!\[\[.*?\]\]", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"[#>*_`~:-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_search_items(
    posts: list[dict],
    sources: Optional[dict[str, str]] = None,
    site_url: str = "",
) -> list[dict]:
    """Build structured search index items from post metadata and optional raw sources."""
    src_map = sources or {}
    base = site_url.rstrip("/")
    items = []
    for p in posts:
        slug = p["slug"]
        raw = src_map.get(slug, "")
        body = _strip_markdown(raw) if raw else p.get("excerpt", "")
        items.append({
            "slug": slug,
            "title": p.get("title", ""),
            "date": p.get("date", ""),
            "tags": p.get("tags", []),
            "excerpt": p.get("excerpt", ""),
            "reading_time": p.get("reading_time", 1),
            "url": f"{base}/posts/{slug}/",
            "body": body[:4000],
        })
    return items


def build_search_index(
    posts: list[dict],
    sources: Optional[dict[str, str]] = None,
    site_url: str = "",
) -> str:
    """Serialize the search index to compact JSON."""
    items = build_search_items(posts, sources=sources, site_url=site_url)
    return json.dumps(items, ensure_ascii=False)


def search_posts(
    posts: list[dict],
    query: str,
    sources: Optional[dict[str, str]] = None,
) -> list[dict]:
    """Rank posts matching whitespace-separated query tokens."""
    q = (query or "").strip().lower()
    if not q:
        return []
    tokens = [t for t in q.split() if t]
    if not tokens:
        return []

    src_map = sources or {}
    scored: list[tuple[int, dict]] = []

    for p in posts:
        title = (p.get("title") or "").lower()
        tags_text = " ".join(str(t).lower() for t in p.get("tags", []))
        excerpt = (p.get("excerpt") or "").lower()
        body = _strip_markdown(src_map.get(p["slug"], "")).lower()

        score = 0
        matched_all = True
        for tok in tokens:
            tok_score = 0
            if tok in title:
                tok_score += 5
            if tok in tags_text:
                tok_score += 3
            if tok in excerpt:
                tok_score += 2
            if tok in body:
                tok_score += 1
            if tok_score == 0:
                matched_all = False
                break
            score += tok_score

        if matched_all and score > 0:
            scored.append((score, p))

    scored.sort(key=lambda pair: (-pair[0], pair[1].get("date", "")), reverse=False)
    # Sort descending by score, then descending by date
    scored.sort(key=lambda pair: (pair[0], pair[1].get("date", "")), reverse=True)
    return [pair[1] for pair in scored]
