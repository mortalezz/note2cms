"""
Local build pipeline — unified Jinja2 renderer writing to local static directory.

Wraps CloudBuildPipeline + LocalDeployer so `rebuild.py` and local workflows share
the exact same rendering, pagination, carousel, and SEO outputs as the API.
"""

import shutil
from pathlib import Path
from typing import Optional

from pipeline.builder_cloud import CloudBuildPipeline
from pipeline.deployer import DeployBatch, LocalDeployer
from pipeline.parser import ParsedPost, parse_markdown


class BuildPipeline:
    def __init__(
        self,
        content_dir: Path,
        static_dir: Path,
        themes_dir: Path,
        active_theme: str,
        site_title: str,
        site_url: str,
        site_lang: str = "en",
        enable_carousel: bool = True,
        search_enabled: bool = False,
        per_page: int = 10,
        pagination_mode: str = "stable",
    ):
        self.content_dir = Path(content_dir)
        self.static_dir = Path(static_dir)
        self.themes_dir = Path(themes_dir)
        self.active_theme = active_theme
        self.site_title = site_title
        self.site_url = site_url.rstrip("/")
        self.site_lang = site_lang
        self.per_page = per_page
        self.pagination_mode = pagination_mode

        self._cloud = CloudBuildPipeline(
            themes_dir=self.themes_dir,
            active_theme=self.active_theme,
            site_title=self.site_title,
            site_url=self.site_url,
            site_lang=self.site_lang,
            enable_carousel=enable_carousel,
            search_enabled=search_enabled,
        )
        self._deployer = LocalDeployer(self.static_dir)

    async def initialize(self):
        """Initialize the Jinja2 renderer and ensure static directory exists."""
        self.static_dir.mkdir(parents=True, exist_ok=True)
        await self._cloud.initialize()

    async def build_post(self, post: ParsedPost, all_posts: Optional[list[dict]] = None) -> Path:
        relations = (
            self._cloud.compute_post_relations(post.slug, all_posts, tags=post.tags, series_name=post.series)
            if all_posts
            else {"prev_post": None, "next_post": None, "related_posts": [], "series_info": None}
        )
        bundle = self._cloud.render_post_bundle(post, **relations)
        batch = DeployBatch()
        batch.add(f"posts/{post.slug}/index.html", bundle.html)
        if bundle.og_png_bytes:
            batch.add(f"posts/assets/{post.slug}/og.png", bundle.og_png_bytes)
        await self._deployer.deploy_batch(batch)
        return self.static_dir / post.slug

    async def build_index(self, posts: list[dict], nav_pages: Optional[list[dict]] = None) -> Path:
        pages_map = self._cloud.render_paginated_index(
            posts,
            per_page=self.per_page,
            mode=self.pagination_mode,
            nav_pages=nav_pages,
        )
        batch = DeployBatch()
        for out_path, html_out in pages_map.items():
            batch.add(out_path, html_out)
        await self._deployer.deploy_batch(batch)
        return self.static_dir / "index.html"

    async def delete_post(self, slug: str) -> None:
        batch = DeployBatch()
        batch.remove_prefix(f"posts/{slug}/")
        batch.remove_prefix(f"posts/assets/{slug}/")
        await self._deployer.deploy_batch(batch)

    async def rebuild_all(self) -> None:
        for item in self.static_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            elif item.name != ".gitkeep":
                item.unlink()

        parsed_posts: list[ParsedPost] = []
        for md_file in sorted(self.content_dir.glob("*.md")):
            raw = md_file.read_text(encoding="utf-8")
            parsed_posts.append(parse_markdown(raw))

        blog_meta = sorted(
            [
                {
                    "slug": p.slug,
                    "title": p.title,
                    "date": p.date,
                    "tags": p.tags,
                    "reading_time": p.reading_time,
                    "excerpt": p.excerpt,
                    "series": p.series or "",
                    "series_order": p.series_order,
                }
                for p in parsed_posts
                if p.post_type == "post"
            ],
            key=lambda x: (x["date"], x["slug"]),
            reverse=True,
        )
        # Ensure tie-break slug ascending for matching dates
        blog_meta.sort(key=lambda x: x["slug"])
        blog_meta.sort(key=lambda x: x["date"], reverse=True)

        nav_pages = [
            {"slug": p.slug, "title": p.title, "permalink": f"{self.site_url}/posts/{p.slug}/"}
            for p in parsed_posts
            if p.post_type == "page"
        ]

        batch = DeployBatch()
        for post in parsed_posts:
            rel = (
                self._cloud.compute_post_relations(post.slug, blog_meta, tags=post.tags, series_name=post.series)
                if post.post_type == "post"
                else {"prev_post": None, "next_post": None, "related_posts": [], "series_info": None}
            )
            bundle = self._cloud.render_post_bundle(post, nav_pages=nav_pages, **rel)
            batch.add(f"posts/{post.slug}/index.html", bundle.html)
            if bundle.og_png_bytes:
                batch.add(f"posts/assets/{post.slug}/og.png", bundle.og_png_bytes)

        for out_path, html_out in self._cloud.render_paginated_index(
            blog_meta,
            per_page=self.per_page,
            mode=self.pagination_mode,
            nav_pages=nav_pages,
        ).items():
            batch.add(out_path, html_out)

        await self._deployer.deploy_batch(batch)
