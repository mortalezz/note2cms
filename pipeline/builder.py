"""
Build pipeline — Vite/React production renderer.

Calls the Node-side render.js which:
  1. Loads the active theme's Post.jsx and Index.jsx
  2. Server-side renders via React renderToString
  3. Wraps in HTML shell with theme CSS
  4. Writes static files

Falls back to Jinja2 templates if Node/render.js is not available.
"""

import os
import shutil
import asyncio
from pathlib import Path
from datetime import datetime

from pipeline.parser import ParsedPost

# Check if the Vite renderer is available
RENDERER_PATH = Path(__file__).parent.parent / "vite-renderer" / "render.js"
USE_VITE = RENDERER_PATH.exists()


class BuildPipeline:
    def __init__(
        self,
        content_dir: Path,
        static_dir: Path,
        themes_dir: Path,
        active_theme: str,
        site_title: str,
        site_url: str,
    ):
        self.content_dir = content_dir
        self.static_dir = static_dir
        self.themes_dir = themes_dir
        self.active_theme = active_theme
        self.site_title = site_title
        self.site_url = site_url
        self._jinja_env = None

    async def initialize(self):
        """Set up the build pipeline."""
        self.static_dir.mkdir(parents=True, exist_ok=True)

        if USE_VITE:
            react_theme = self.themes_dir / self.active_theme / "react"
            if not (react_theme / "Post.jsx").exists():
                raise FileNotFoundError(
                    f"React theme not found at {react_theme}/Post.jsx"
                )
            print(f"[build] Using Vite/React renderer: {RENDERER_PATH}")
        else:
            from jinja2 import Environment, FileSystemLoader
            theme_path = self.themes_dir / self.active_theme
            if not theme_path.exists():
                raise FileNotFoundError(f"Theme '{self.active_theme}' not found")
            self._jinja_env = Environment(
                loader=FileSystemLoader(str(theme_path)),
                autoescape=False,
            )
            print(f"[build] Using Jinja2 fallback renderer")

    async def build_post(self, post: ParsedPost) -> Path:
        if USE_VITE:
            return await self._build_post_vite(post)
        return await self._build_post_jinja(post)

    async def build_index(self, posts: list[dict]) -> Path:
        if USE_VITE:
            return await self._build_index_vite()
        return await self._build_index_jinja(posts)

    async def delete_post(self, slug: str) -> None:
        post_dir = self.static_dir / slug
        if post_dir.exists():
            shutil.rmtree(post_dir)

    async def rebuild_all(self) -> None:
        if USE_VITE:
            await self._run_renderer([])
        else:
            from pipeline.parser import parse_markdown
            for item in self.static_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                elif item.name != ".gitkeep":
                    item.unlink()
            for md_file in sorted(self.content_dir.glob("*.md")):
                raw = md_file.read_text(encoding="utf-8")
                post = parse_markdown(raw)
                await self._build_post_jinja(post)

    # --- Vite/React ---

    async def _build_post_vite(self, post: ParsedPost) -> Path:
        await self._run_renderer(["--slug", post.slug])
        return self.static_dir / post.slug

    async def _build_index_vite(self) -> Path:
        await self._run_renderer(["--index-only"])
        return self.static_dir / "index.html"

    async def _run_renderer(self, args: list[str]) -> None:
        env = {
            **os.environ,
            "CONTENT_DIR": str(self.content_dir),
            "STATIC_DIR": str(self.static_dir),
            "THEMES_DIR": str(self.themes_dir),
            "ACTIVE_THEME": self.active_theme,
            "SITE_TITLE": self.site_title,
            "SITE_URL": self.site_url,
            "NODE_NO_WARNINGS": "1",
        }

        cmd = ["node", "--experimental-vm-modules", str(RENDERER_PATH)] + args

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            cwd=str(RENDERER_PATH.parent.parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        if stdout:
            for line in stdout.decode().strip().split("\n"):
                print(f"[vite] {line}")

        if proc.returncode != 0:
            error_msg = stderr.decode().strip()
            print(f"[vite] ERROR: {error_msg}")
            raise RuntimeError(f"Vite renderer failed: {error_msg}")

    # --- Jinja2 fallback ---

    async def _build_post_jinja(self, post: ParsedPost) -> Path:
        import markdown as md_lib

        converter = md_lib.Markdown(
            extensions=["fenced_code", "codehilite", "tables", "toc", "smarty"],
            extension_configs={
                "codehilite": {"css_class": "highlight", "linenums": False},
            },
        )
        html_content = converter.convert(post.content)

        try:
            dt = datetime.fromisoformat(post.date)
            display_date = dt.strftime("%B %-d, %Y")
        except (ValueError, AttributeError):
            display_date = post.date

        template = self._jinja_env.get_template("post.html")
        rendered = template.render(
            title=post.title,
            date=display_date,
            date_iso=post.date,
            content=html_content,
            tags=post.tags,
            reading_time=post.reading_time,
            slug=post.slug,
            site_title=self.site_title,
            site_url=self.site_url,
            excerpt=post.excerpt,
        )

        post_dir = self.static_dir / post.slug
        post_dir.mkdir(parents=True, exist_ok=True)
        (post_dir / "index.html").write_text(rendered, encoding="utf-8")
        return post_dir

    async def _build_index_jinja(self, posts: list[dict]) -> Path:
        formatted_posts = []
        for p in posts:
            try:
                dt = datetime.fromisoformat(p["date"])
                display_date = dt.strftime("%B %-d, %Y")
            except (ValueError, AttributeError):
                display_date = p["date"]
            formatted_posts.append({
                **p,
                "display_date": display_date,
                "permalink": f"/posts/{p['slug']}/",
            })

        template = self._jinja_env.get_template("index.html")
        rendered = template.render(
            posts=formatted_posts,
            site_title=self.site_title,
            site_url=self.site_url,
        )
        output = self.static_dir / "index.html"
        output.write_text(rendered, encoding="utf-8")
        return output
