"""
Migrator helper: recovers posts and metadata from published GitHub Pages.
"""

import re
import html
import json
import math
import urllib.request
import urllib.error
from datetime import datetime, timezone

try:
    import markdownify
except ImportError:
    markdownify = None


def estimate_reading_time(text: str, wpm: int = 220) -> int:
    words = len(text.split())
    return max(1, math.ceil(words / wpm))


def get_post_slugs(repo: str, branch: str = "gh-pages", token: str = None) -> list[str]:
    """Fetch list of post slugs from GitHub Git tree or fallback to HTML index."""
    headers = {"User-Agent": "note2cms-migrator"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    api_url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            slugs = []
            for item in data.get("tree", []):
                p = item.get("path", "")
                if p.startswith("posts/") and p.endswith("/index.html"):
                    parts = p.split("/")
                    if len(parts) == 3 and parts[1] != "index.html":
                        slugs.append(parts[1])
            if slugs:
                return sorted(list(set(slugs)))
    except Exception as e:
        print(f"[migrator] GitHub API tree request failed ({e}). Falling back to HTML scraping...")

    # Fallback: scrape from blog index HTML
    owner, repo_name = repo.split("/")
    index_url = f"https://{owner}.github.io/{repo_name}/"
    try:
        req = urllib.request.Request(index_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            index_html = resp.read().decode("utf-8")
            found = re.findall(r'href="[^"]*/posts/([^/"]+)/?"', index_html)
            slugs = [s for s in found if s and s != "index.html"]
            return sorted(list(set(slugs)))
    except Exception as e:
        print(f"[migrator] Fallback scraping failed: {e}")
        return []


def fetch_and_parse_post(repo: str, branch: str = "gh-pages", slug: str = "", token: str = None) -> dict:
    """Fetch post HTML and reconstruct metadata and markdown."""
    raw_url = f"https://raw.githubusercontent.com/{repo}/{branch}/posts/{slug}/index.html"
    headers = {"User-Agent": "note2cms-migrator"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        req = urllib.request.Request(raw_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_html = resp.read().decode("utf-8")
    except urllib.error.HTTPError:
        owner, repo_name = repo.split("/")
        alt_url = f"https://{owner}.github.io/{repo_name}/posts/{slug}/index.html"
        req = urllib.request.Request(alt_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_html = resp.read().decode("utf-8")

    title_m = re.search(r'<meta property="og:title" content="(.*?)"', content_html)
    if not title_m:
        title_m = re.search(r'<title>(.*?) —', content_html)
    title = html.unescape(title_m.group(1)).strip() if title_m else slug

    date_m = re.search(r'<time datetime="(.*?)"', content_html)
    date_str = date_m.group(1).strip() if date_m else datetime.now(timezone.utc).isoformat()

    desc_m = re.search(r'<meta name="description" content="(.*?)"', content_html, re.DOTALL)
    excerpt = html.unescape(desc_m.group(1)).strip() if desc_m else ""

    tags_m = re.findall(r'<div class="post-tags">\s*(.*?)\s*</div>', content_html, re.DOTALL)
    tags = []
    if tags_m:
        tags = [html.unescape(t).strip().lower() for t in re.findall(r'<span>(.*?)</span>', tags_m[0])]

    body_m = re.search(r'<div class="post-content">(.*?)</div>\s*</article>', content_html, re.DOTALL)
    body_html = body_m.group(1).strip() if body_m else ""

    if markdownify is not None:
        body_md = markdownify.markdownify(
            body_html,
            heading_style="ATX",
            bullets="-",
            code_language="",
        ).strip()
    else:
        body_md = body_html

    reading_time = estimate_reading_time(body_md)

    yaml_lines = [
        "---",
        f'title: "{title}"',
        f'date: "{date_str}"',
        f'slug: "{slug}"',
    ]
    if tags:
        yaml_lines.append("tags:")
        for t in tags:
            yaml_lines.append(f'  - "{t}"')
    if excerpt:
        escaped_excerpt = excerpt.replace('"', '\\"').replace("\n", " ")
        yaml_lines.append(f'excerpt: "{escaped_excerpt}"')
    yaml_lines.append("---")
    yaml_lines.append("")
    yaml_lines.append(body_md)
    yaml_lines.append("")

    full_markdown = "\n".join(yaml_lines)

    return {
        "slug": slug,
        "title": title,
        "date": date_str,
        "tags": tags,
        "reading_time": reading_time,
        "excerpt": excerpt,
        "markdown": full_markdown,
    }
