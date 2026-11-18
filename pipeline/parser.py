"""
Markdown parser — the contract between your notes and the pipelines.

Frontmatter spec (minimal by design):
  Required: title
  Optional: tags, date, slug, excerpt, cover, series, series_order, type, carousel

Everything else is derived.
"""

import re
import math
from dataclasses import dataclass
from datetime import date as date_type, datetime, timezone
from typing import Any, Optional

import frontmatter
from slugify import slugify


@dataclass
class ParsedPost:
    title: str
    slug: str
    date: str  # Normalized UTC ISO-8601 format
    tags: list[str]
    content: str  # Raw markdown body (no frontmatter)
    excerpt: str
    reading_time: int  # minutes
    raw_markdown: str  # Original full markdown including frontmatter
    cover: Optional[str] = None
    series: Optional[str] = None
    series_order: Optional[int] = None
    post_type: str = "post"
    carousel: bool = True


def _normalize_date(date_val: Any) -> str:
    """Normalize a frontmatter date value into a UTC ISO-8601 string."""
    if not date_val:
        return datetime.now(timezone.utc).isoformat()

    if isinstance(date_val, datetime):
        dt = date_val if date_val.tzinfo else date_val.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    if isinstance(date_val, date_type):
        dt = datetime(date_val.year, date_val.month, date_val.day, tzinfo=timezone.utc)
        return dt.isoformat()

    raw_str = str(date_val).strip()
    if not raw_str:
        return datetime.now(timezone.utc).isoformat()

    iso_candidate = raw_str[:-1] + "+00:00" if raw_str.endswith("Z") else raw_str
    try:
        dt = datetime.fromisoformat(iso_candidate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw_str, fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue

    return raw_str


def _estimate_reading_time(text: str, wpm: int = 220) -> int:
    """Estimate reading time in minutes. Rounds up, minimum 1."""
    words = len(text.split())
    return max(1, math.ceil(words / wpm))


def _extract_excerpt(content: str, max_chars: int = 200) -> str:
    """
    Pull the first paragraph as excerpt.
    Strip markdown formatting for clean display.
    """
    # Remove gallery container lines
    clean = re.sub(r"^:::\s*gallery.*$", "", content, flags=re.MULTILINE)
    clean = re.sub(r"^:::\s*$", "", clean, flags=re.MULTILINE)
    # Remove Obsidian embeds ![[...]]
    clean = re.sub(r"!\[\[.*?\]\]", "", clean)
    # Remove headers
    clean = re.sub(r"^#{1,6}\s+", "", clean, flags=re.MULTILINE)
    # Remove images
    clean = re.sub(r"!\[.*?\]\(.*?\)", "", clean)
    # Remove links but keep text
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
    # Convert Obsidian wikilinks to display text
    clean = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", clean)
    clean = re.sub(r"\[\[([^\]]+)\]\]", r"\1", clean)
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
    - cover (optional cover image URL/asset name)
    - series (optional series name)
    - series_order (optional integer order within series)
    - type / post_type (optional: "post" or "page")
    - carousel (optional bool, default True)
    """
    post = frontmatter.loads(raw)
    metadata = post.metadata
    content = post.content

    # Title is the one required field
    title = metadata.get("title")
    if not title:
        raise ValueError("Frontmatter must include 'title'")
    title = str(title).strip()

    # Slug: explicit or derived from title
    raw_slug = metadata.get("slug")
    if raw_slug:
        slug = slugify(str(raw_slug), max_length=80) or str(raw_slug).strip()
    else:
        slug = slugify(title, max_length=80) or "post"

    # Date: normalized UTC ISO string
    date_str = _normalize_date(metadata.get("date"))

    # Tags: normalize to list of unique non-empty lowercase strings
    tags_raw = metadata.get("tags", [])
    if tags_raw is None:
        tags_raw = []
    if isinstance(tags_raw, str):
        parsed_tags = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]
    else:
        parsed_tags = [str(t).strip().lower() for t in tags_raw if str(t).strip()]
    tags = list(dict.fromkeys(parsed_tags))

    # Excerpt: explicit or derived
    excerpt_raw = metadata.get("excerpt")
    excerpt = str(excerpt_raw).strip() if excerpt_raw else _extract_excerpt(content)

    # Optional extended metadata
    cover_raw = metadata.get("cover")
    cover = str(cover_raw).strip() if cover_raw else None

    series_raw = metadata.get("series")
    series = str(series_raw).strip() if series_raw else None

    series_order_raw = metadata.get("series_order")
    series_order: Optional[int] = None
    if series_order_raw is not None and str(series_order_raw).strip() != "":
        try:
            series_order = int(series_order_raw)
        except (TypeError, ValueError):
            series_order = None

    type_raw = str(metadata.get("type") or metadata.get("post_type") or "post").strip().lower()
    post_type = "page" if type_raw == "page" else "post"

    carousel_raw = metadata.get("carousel", True)
    if isinstance(carousel_raw, str):
        carousel = carousel_raw.strip().lower() not in ("false", "0", "no", "off")
    else:
        carousel = bool(carousel_raw)

    return ParsedPost(
        title=title,
        slug=slug,
        date=date_str,
        tags=tags,
        content=content,
        excerpt=excerpt,
        reading_time=_estimate_reading_time(content),
        raw_markdown=raw,
        cover=cover,
        series=series,
        series_order=series_order,
        post_type=post_type,
        carousel=carousel,
    )
