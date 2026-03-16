"""
Markdown parser — the contract between your notes and the pipelines.

Frontmatter spec (minimal by design):
  Required: title
  Optional: tags, date, slug, excerpt

Everything else is derived.
"""

import re
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import frontmatter
from slugify import slugify


@dataclass
class ParsedPost:
    title: str
    slug: str
    date: str  # ISO format
    tags: list[str]
    content: str  # Raw markdown body (no frontmatter)
    excerpt: str
    reading_time: int  # minutes
    raw_markdown: str  # Original full markdown including frontmatter


def _estimate_reading_time(text: str, wpm: int = 220) -> int:
    """Estimate reading time in minutes. Rounds up, minimum 1."""
    words = len(text.split())
    return max(1, math.ceil(words / wpm))


def _extract_excerpt(content: str, max_chars: int = 200) -> str:
    """
    Pull the first paragraph as excerpt.
    Strip markdown formatting for clean display.
    """
    # Remove headers
    clean = re.sub(r"^#{1,6}\s+", "", content, flags=re.MULTILINE)
    # Remove images
    clean = re.sub(r"!\[.*?\]\(.*?\)", "", clean)
    # Remove links but keep text
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
    # Remove bold/italic markers
    clean = re.sub(r"[*_]{1,3}", "", clean)
    # Remove code blocks
    clean = re.sub(r"```[\s\S]*?```", "", clean)
    clean = re.sub(r"`[^`]+`", "", clean)

    # Get first non-empty paragraph
    paragraphs = [p.strip() for p in clean.split("\n\n") if p.strip()]
    if not paragraphs:
        return ""

    excerpt = paragraphs[0]
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rsplit(" ", 1)[0] + "…"
    return excerpt


def parse_markdown(raw: str) -> ParsedPost:
    """
    Parse raw Markdown with frontmatter into a structured post object.

    The frontmatter contract is intentionally minimal:
    - title (required — will error without it)
    - tags (optional, defaults to [])
    - date (optional, defaults to now)
    - slug (optional, derived from title)
    - excerpt (optional, derived from first paragraph)
    """
    post = frontmatter.loads(raw)
    metadata = post.metadata
    content = post.content

    # Title is the one required field
    title = metadata.get("title")
    if not title:
        raise ValueError("Frontmatter must include 'title'")

    # Slug: explicit or derived from title
    slug = metadata.get("slug") or slugify(title, max_length=80)

    # Date: explicit or now
    date_val = metadata.get("date")
    if date_val:
        if isinstance(date_val, datetime):
            date_str = date_val.isoformat()
        else:
            date_str = str(date_val)
    else:
        date_str = datetime.now(timezone.utc).isoformat()

    # Tags: normalize to list of lowercase strings
    tags_raw = metadata.get("tags", [])
    if isinstance(tags_raw, str):
        tags = [t.strip().lower() for t in tags_raw.split(",")]
    else:
        tags = [str(t).strip().lower() for t in tags_raw]

    # Excerpt: explicit or derived
    excerpt = metadata.get("excerpt") or _extract_excerpt(content)

    return ParsedPost(
        title=title,
        slug=slug,
        date=date_str,
        tags=tags,
        content=content,
        excerpt=excerpt,
        reading_time=_estimate_reading_time(content),
        raw_markdown=raw,
    )
