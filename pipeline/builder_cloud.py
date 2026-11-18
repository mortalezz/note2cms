"""
Unified Jinja2 build pipeline — renders posts, paginated indexes, tag archives,
search pages, and OG cards in memory with zero Node/Vite dependencies.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from pipeline.i18n import format_date, get_translations, normalize_lang
from pipeline.markdown_ext import render_markdown
from pipeline.media import ProcessedAsset, resolve_asset_match
from pipeline.og import generate_og_image
from pipeline.paginator import PageSlice, paginate_posts
from pipeline.parser import ParsedPost


@dataclass
class RenderedPostBundle:
    html: str
    body_html: str
    og_image_url: str
    og_png_bytes: Optional[bytes]
    first_image_url: Optional[str]


def _full_url(site_url: str, maybe_rel: str) -> str:
    if not maybe_rel:
        return ""
    if maybe_rel.startswith(("http://", "https://")):
        return maybe_rel
    base = site_url.rstrip("/")
    if maybe_rel.startswith("/"):
        return f"{base}{maybe_rel}"
    return f"{base}/{maybe_rel}"


class CloudBuildPipeline:
    """
    Renders posts, paginated indexes, tag pages, and search pages to HTML strings.
    No filesystem side effects.
    """

    def __init__(
        self,
        themes_dir: Path,
        active_theme: str,
        site_title: str,
        site_url: str,
        site_lang: str = "en",
        enable_carousel: bool = True,
        search_enabled: bool = False,
    ):
        self.themes_dir = Path(themes_dir)
        self.active_theme = active_theme
        self.site_title = site_title
        self.site_url = site_url.rstrip("/")
        self.site_lang = normalize_lang(site_lang)
        self.enable_carousel = enable_carousel
        self.search_enabled = search_enabled
        self.jinja_env: Optional[Environment] = None
        self._shared_css_cache: str = ""

    async def initialize(self):
        """Set up the Jinja2 template environment with shared partial support."""
        theme_path = self.themes_dir / self.active_theme
        if not theme_path.exists():
            raise FileNotFoundError(
                f"Theme '{self.active_theme}' not found at {theme_path}"
            )

        shared_dir = self.themes_dir / "_shared"
        loaders = [FileSystemLoader(str(theme_path)), FileSystemLoader(str(self.themes_dir))]
        if shared_dir.exists():
            loaders.append(FileSystemLoader(str(shared_dir)))
            css_path = shared_dir / "components.css"
            if css_path.exists():
                self._shared_css_cache = css_path.read_text(encoding="utf-8")

        self.jinja_env = Environment(
            loader=ChoiceLoader(loaders),
            autoescape=select_autoescape(enabled_extensions=("html", "xml"), default=True),
        )
        print(f"[build] Jinja2 pipeline using theme: {self.active_theme} (lang={self.site_lang})")

    def _inject_fallback_css(self, html: str) -> str:
        """Ensure custom third-party themes without _shared include still get component styles."""
        if (
            self._shared_css_cache
            and "/* note2cms shared components" not in html
            and "</head>" in html
        ):
            return html.replace(
                "</head>",
                f"<style>{self._shared_css_cache}</style>\n</head>",
                1,
            )
        return html

    def _format_summary_items(self, posts: list[dict]) -> list[dict]:
        formatted = []
        for p in posts:
            formatted.append({
                **p,
                "display_date": format_date(p.get("date", ""), self.site_lang),
                "permalink": f"{self.site_url}/posts/{p['slug']}/",
            })
        return formatted

    def compute_post_relations(
        self,
        slug: str,
        all_posts: list[dict],
        *,
        tags: Optional[list[str]] = None,
        series_name: Optional[str] = None,
    ) -> dict:
        """
        Compute prev_post (older), next_post (newer), related_posts (shared tags),
        and series_info for a single post given newest-first `all_posts`.
        """
        idx = next((i for i, p in enumerate(all_posts) if p.get("slug") == slug), None)
        next_post = None
        prev_post = None
        if idx is not None:
            if idx > 0:
                np = all_posts[idx - 1]
                next_post = {
                    "slug": np["slug"],
                    "title": np["title"],
                    "permalink": f"{self.site_url}/posts/{np['slug']}/",
                }
            if idx + 1 < len(all_posts):
                pp = all_posts[idx + 1]
                prev_post = {
                    "slug": pp["slug"],
                    "title": pp["title"],
                    "permalink": f"{self.site_url}/posts/{pp['slug']}/",
                }

        # Related posts: overlap in tags
        post_tags = set(tags or (all_posts[idx].get("tags", []) if idx is not None else []))
        related: list[tuple[int, dict]] = []
        if post_tags:
            for p in all_posts:
                if p.get("slug") == slug:
                    continue
                overlap = len(post_tags & set(p.get("tags", [])))
                if overlap > 0:
                    related.append((overlap, p))
            related.sort(key=lambda pair: (pair[0], pair[1].get("date", "")), reverse=True)

        related_posts = self._format_summary_items([pair[1] for pair in related[:3]])

        # Series info
        series_info = None
        target_series = series_name or (all_posts[idx].get("series") if idx is not None else None)
        if target_series:
            peers = [p for p in all_posts if p.get("series") == target_series]
            # Sort by series_order (None last), then chronological date ASC, then slug
            peers.sort(
                key=lambda p: (
                    p.get("series_order") is None,
                    p.get("series_order") if p.get("series_order") is not None else 0,
                    p.get("date", ""),
                    p.get("slug", ""),
                )
            )
            if peers:
                current_pos = 1
                items = []
                for pos, peer in enumerate(peers, start=1):
                    is_curr = peer.get("slug") == slug
                    if is_curr:
                        current_pos = pos
                    items.append({
                        "slug": peer["slug"],
                        "title": peer["title"],
                        "permalink": f"{self.site_url}/posts/{peer['slug']}/",
                        "is_current": is_curr,
                    })
                series_info = {
                    "name": target_series,
                    "current_index": current_pos,
                    "total": len(items),
                    "posts": items,
                }

        return {
            "prev_post": prev_post,
            "next_post": next_post,
            "related_posts": related_posts,
            "series_info": series_info,
        }

    def render_post_bundle(
        self,
        post: ParsedPost,
        *,
        assets_map: Optional[dict[str, ProcessedAsset]] = None,
        prev_post: Optional[dict] = None,
        next_post: Optional[dict] = None,
        related_posts: Optional[list[dict]] = None,
        series_info: Optional[dict] = None,
        og_image: Optional[str] = None,
        nav_pages: Optional[list[dict]] = None,
        generate_og_card: bool = True,
    ) -> RenderedPostBundle:
        """Render a post (or static page) to HTML + optional generated OG PNG card."""
        use_carousel = self.enable_carousel and getattr(post, "carousel", True)
        rendered_md = render_markdown(
            post.content,
            assets_map=assets_map,
            enable_carousel=use_carousel,
            lang=self.site_lang,
        )

        display_date = format_date(post.date, self.site_lang)
        i18n = get_translations(self.site_lang)

        # Resolve OG image: explicit override -> post.cover -> first image -> generated card
        resolved_og = ""
        og_png_bytes: Optional[bytes] = None
        if og_image:
            resolved_og = _full_url(self.site_url, og_image)
        elif getattr(post, "cover", None):
            matched_cover = resolve_asset_match(post.cover, assets_map or {})
            if matched_cover:
                resolved_og = _full_url(self.site_url, matched_cover.primary_url)
            else:
                resolved_og = _full_url(self.site_url, post.cover)
        elif rendered_md.first_image_url:
            resolved_og = _full_url(self.site_url, rendered_md.first_image_url)
        elif generate_og_card:
            og_png_bytes = generate_og_image(
                title=post.title,
                site_title=self.site_title,
                date_str=display_date,
                reading_time=post.reading_time,
                tags=post.tags,
                theme=self.active_theme,
                min_read_label=i18n["min_read"],
            )
            resolved_og = f"{self.site_url}/posts/assets/{post.slug}/og.png"

        template = self.jinja_env.get_template("post.html")
        is_page = getattr(post, "post_type", "post") == "page"
        html_out = template.render(
            title=post.title,
            date=display_date,
            date_iso=post.date,
            content=Markup(rendered_md.html),
            tags=[] if is_page else post.tags,
            reading_time=post.reading_time,
            slug=post.slug,
            site_title=self.site_title,
            site_url=self.site_url,
            excerpt=post.excerpt,
            site_lang=self.site_lang,
            i18n=i18n,
            og_image=resolved_og,
            prev_post=None if is_page else prev_post,
            next_post=None if is_page else next_post,
            related_posts=[] if is_page else (related_posts or []),
            series_info=None if is_page else series_info,
            nav_pages=nav_pages or [],
            search_enabled=self.search_enabled,
        )
        html_out = self._inject_fallback_css(html_out)

        return RenderedPostBundle(
            html=html_out,
            body_html=rendered_md.html,
            og_image_url=resolved_og,
            og_png_bytes=og_png_bytes,
            first_image_url=rendered_md.first_image_url,
        )

    def render_post(
        self,
        post: ParsedPost,
        *,
        assets_map: Optional[dict[str, ProcessedAsset]] = None,
        prev_post: Optional[dict] = None,
        next_post: Optional[dict] = None,
        related_posts: Optional[list[dict]] = None,
        series_info: Optional[dict] = None,
        og_image: Optional[str] = None,
        nav_pages: Optional[list[dict]] = None,
    ) -> str:
        """Render a single post to an HTML string."""
        return self.render_post_bundle(
            post,
            assets_map=assets_map,
            prev_post=prev_post,
            next_post=next_post,
            related_posts=related_posts,
            series_info=series_info,
            og_image=og_image,
            nav_pages=nav_pages,
            generate_og_card=False,
        ).html

    def render_index_slice(
        self,
        page_slice: PageSlice,
        *,
        nav_pages: Optional[list[dict]] = None,
        active_tag: Optional[str] = None,
    ) -> str:
        """Render a single paginated index (or tag archive) PageSlice to HTML."""
        formatted_posts = self._format_summary_items(page_slice.posts)
        i18n = get_translations(self.site_lang)
        template = self.jinja_env.get_template("index.html")
        html_out = template.render(
            posts=formatted_posts,
            pagination=page_slice,
            site_title=self.site_title,
            site_url=self.site_url,
            site_lang=self.site_lang,
            i18n=i18n,
            nav_pages=nav_pages or [],
            active_tag=active_tag,
            tags_overview=False,
            search_page=False,
            search_enabled=self.search_enabled,
        )
        return self._inject_fallback_css(html_out)

    def render_paginated_index(
        self,
        posts: list[dict],
        *,
        per_page: int = 10,
        mode: str = "stable",
        prefix: str = "/posts",
        include_root_index: bool = True,
        nav_pages: Optional[list[dict]] = None,
        active_tag: Optional[str] = None,
    ) -> dict[str, str]:
        """Render all PageSlices for an index or tag archive into `{path: html}`."""
        slices = paginate_posts(
            posts,
            per_page=per_page,
            mode=mode,
            base_url=self.site_url,
            prefix=prefix,
            include_root_index=include_root_index,
        )
        outputs: dict[str, str] = {}
        for page_slice in slices:
            html_out = self.render_index_slice(
                page_slice,
                nav_pages=nav_pages,
                active_tag=active_tag,
            )
            for out_path in page_slice.output_paths:
                outputs[out_path] = html_out
        return outputs

    def render_index(self, posts: list[dict]) -> str:
        """Render a single unpaginated index page (backward-compatible helper)."""
        slices = paginate_posts(
            posts,
            per_page=max(1, len(posts) or 10),
            mode="stable",
            base_url=self.site_url,
            prefix="/posts",
        )
        return self.render_index_slice(slices[0])

    def render_tags_overview(
        self,
        all_tags: dict[str, int],
        *,
        nav_pages: Optional[list[dict]] = None,
    ) -> str:
        """Render the `/posts/tags/` overview page."""
        i18n = get_translations(self.site_lang)
        template = self.jinja_env.get_template("index.html")
        html_out = template.render(
            posts=[],
            pagination=None,
            site_title=self.site_title,
            site_url=self.site_url,
            site_lang=self.site_lang,
            i18n=i18n,
            nav_pages=nav_pages or [],
            active_tag=None,
            tags_overview=True,
            all_tags=all_tags,
            search_page=False,
            search_enabled=self.search_enabled,
        )
        return self._inject_fallback_css(html_out)

    def render_search_page(
        self,
        *,
        nav_pages: Optional[list[dict]] = None,
    ) -> str:
        """Render the `/posts/search/` static search page."""
        i18n = get_translations(self.site_lang)
        template = self.jinja_env.get_template("index.html")
        html_out = template.render(
            posts=[],
            pagination=None,
            site_title=self.site_title,
            site_url=self.site_url,
            site_lang=self.site_lang,
            i18n=i18n,
            nav_pages=nav_pages or [],
            active_tag=None,
            tags_overview=False,
            search_page=True,
            search_enabled=True,
        )
        return self._inject_fallback_css(html_out)
