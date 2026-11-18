"""
Feed & SEO artifact generators: RSS 2.0, Atom 1.0, sitemap.xml, robots.txt.
"""

from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import quote
from xml.sax.saxutils import escape


def _parse_iso_dt(date_str: str) -> datetime:
    try:
        raw = str(date_str).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _cdata(text: str) -> str:
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def render_rss(
    posts: list[dict],
    site_title: str,
    site_url: str,
    lang: str = "en",
    full_text: bool = True,
    rendered_bodies: dict[str, str] | None = None,
    max_items: int = 30,
) -> str:
    """Generate an RSS 2.0 XML document."""
    base = site_url.rstrip("/")
    bodies = rendered_bodies or {}
    items_slice = posts[:max_items]
    last_build = format_datetime(
        _parse_iso_dt(items_slice[0]["date"]) if items_slice else datetime.now(timezone.utc)
    )

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        f"  <title>{escape(site_title)}</title>",
        f"  <link>{escape(base + '/posts/')}</link>",
        f"  <description>{escape(site_title)} — writing, published from notes.</description>",
        f"  <language>{escape(lang)}</language>",
        f"  <lastBuildDate>{escape(last_build)}</lastBuildDate>",
        f'  <atom:link href="{escape(base + "/feed.xml")}" rel="self" type="application/rss+xml"/>',
    ]

    for post in items_slice:
        slug = post["slug"]
        link = f"{base}/posts/{slug}/"
        pub_date = format_datetime(_parse_iso_dt(post["date"]))
        excerpt = post.get("excerpt", "")
        body_html = bodies.get(slug, "")

        lines.append("  <item>")
        lines.append(f"    <title>{escape(post['title'])}</title>")
        lines.append(f"    <link>{escape(link)}</link>")
        lines.append(f'    <guid isPermaLink="true">{escape(link)}</guid>')
        lines.append(f"    <pubDate>{escape(pub_date)}</pubDate>")
        lines.append(f"    <description>{escape(excerpt)}</description>")
        for tag in post.get("tags", []):
            lines.append(f"    <category>{escape(str(tag))}</category>")
        if full_text and body_html:
            lines.append(f"    <content:encoded>{_cdata(body_html)}</content:encoded>")
        lines.append("  </item>")

    lines.append("</channel>")
    lines.append("</rss>")
    return "\n".join(lines) + "\n"


def render_atom(
    posts: list[dict],
    site_title: str,
    site_url: str,
    full_text: bool = True,
    rendered_bodies: dict[str, str] | None = None,
    max_items: int = 30,
) -> str:
    """Generate an Atom 1.0 XML document."""
    base = site_url.rstrip("/")
    bodies = rendered_bodies or {}
    items_slice = posts[:max_items]
    updated_iso = (
        _parse_iso_dt(items_slice[0]["date"]).isoformat()
        if items_slice
        else datetime.now(timezone.utc).isoformat()
    )

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f"  <title>{escape(site_title)}</title>",
        f'  <link href="{escape(base + "/posts/")}"/>',
        f'  <link href="{escape(base + "/atom.xml")}" rel="self" type="application/atom+xml"/>',
        f"  <id>{escape(base + '/')}</id>",
        f"  <updated>{escape(updated_iso)}</updated>",
    ]

    for post in items_slice:
        slug = post["slug"]
        link = f"{base}/posts/{slug}/"
        post_dt = _parse_iso_dt(post["date"]).isoformat()
        excerpt = post.get("excerpt", "")
        body_html = bodies.get(slug, "")

        lines.append("  <entry>")
        lines.append(f"    <title>{escape(post['title'])}</title>")
        lines.append(f'    <link href="{escape(link)}"/>')
        lines.append(f"    <id>{escape(link)}</id>")
        lines.append(f"    <updated>{escape(post_dt)}</updated>")
        lines.append(f"    <summary>{escape(excerpt)}</summary>")
        for tag in post.get("tags", []):
            lines.append(f'    <category term="{escape(str(tag))}"/>')
        if full_text and body_html:
            lines.append(f'    <content type="html">{escape(body_html)}</content>')
        lines.append("  </entry>")

    lines.append("</feed>")
    return "\n".join(lines) + "\n"


def render_sitemap(
    posts: list[dict],
    pages: list[dict],
    tags: list[str],
    site_url: str,
) -> str:
    """Generate sitemap.xml covering index, posts, static pages, and tag pages."""
    base = site_url.rstrip("/")
    urls: list[tuple[str, str]] = [
        (f"{base}/", ""),
        (f"{base}/posts/", ""),
        (f"{base}/posts/tags/", ""),
    ]

    for post in posts:
        dt = _parse_iso_dt(post["date"]).date().isoformat()
        urls.append((f"{base}/posts/{post['slug']}/", dt))

    for page in pages:
        dt = _parse_iso_dt(page["date"]).date().isoformat()
        urls.append((f"{base}/posts/{page['slug']}/", dt))

    for tag in sorted(set(tags)):
        urls.append((f"{base}/posts/tags/{quote(tag)}/", ""))

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemxml.org/schemas/sitemap/0.9">',
    ]
    # Use standard sitemaps.org namespace
    lines[1] = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'

    for loc, lastmod in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(loc)}</loc>")
        if lastmod:
            lines.append(f"    <lastmod>{escape(lastmod)}</lastmod>")
        lines.append("  </url>")

    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def render_robots(site_url: str) -> str:
    """Generate robots.txt pointing to sitemap.xml."""
    base = site_url.rstrip("/")
    return f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"
