"""
Cloud build pipeline — renders HTML in memory, returns strings.

No filesystem writes. The caller (the API) decides where the HTML goes:
local filesystem, GitHub Pages, S3, wherever.

Uses Jinja2 for the MVP. The JSX/Vite path produces identical output
but requires a Node process — swap it in when you need it.
"""

from pathlib import Path
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

from pipeline.parser import ParsedPost


class CloudBuildPipeline:
    """
    Renders posts and index pages to HTML strings.
    No filesystem side effects.
    """

    def __init__(
        self,
        themes_dir: Path,
        active_theme: str,
        site_title: str,
        site_url: str,
    ):
        self.themes_dir = themes_dir
        self.active_theme = active_theme
        self.site_title = site_title
        self.site_url = site_url
        self.jinja_env = None

    async def initialize(self):
        """Set up the Jinja2 template environment."""
        theme_path = self.themes_dir / self.active_theme
        if not theme_path.exists():
            raise FileNotFoundError(
                f"Theme '{self.active_theme}' not found at {theme_path}"
            )

        self.jinja_env = Environment(
            loader=FileSystemLoader(str(theme_path)),
            autoescape=False,
        )
        print(f"[build] Cloud pipeline using theme: {self.active_theme}")

    def render_post(self, post: ParsedPost) -> str:
        """Render a single post to an HTML string."""
        import markdown

        md = markdown.Markdown(
            extensions=[
                "fenced_code", "codehilite", "tables",
                "toc", "smarty", "attr_list", "md_in_html",
            ],
            extension_configs={
                "codehilite": {"css_class": "highlight", "linenums": False},
                "smarty": {"smart_quotes": True},
            },
        )
        html_content = md.convert(post.content)

        try:
            dt = datetime.fromisoformat(post.date)
            display_date = dt.strftime("%B %-d, %Y")
        except (ValueError, AttributeError):
            display_date = post.date

        template = self.jinja_env.get_template("post.html")
        return template.render(
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

    def render_index(self, posts: list[dict]) -> str:
        """Render the index page to an HTML string."""
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
                "permalink": f"{self.site_url}/posts/{p['slug']}/",
            })

        template = self.jinja_env.get_template("index.html")
        return template.render(
            posts=formatted_posts,
            site_title=self.site_title,
            site_url=self.site_url,
        )
