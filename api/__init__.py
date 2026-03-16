"""
note2cms — Past-Browser Publishing Protocol
4 endpoints. That's the whole CMS.

Deployment modes:
  LOCAL:  SQLite taxonomy + local filesystem for content/static
  CLOUD:  PostgreSQL taxonomy + GitHub Pages for static output
          (Markdown source stored in DB, no filesystem writes needed)
"""

import os
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel, Field

from pipeline.parser import parse_markdown
from pipeline.taxonomy_pg import get_taxonomy_db

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_TOKEN = os.getenv("API_TOKEN", "CHANGE_ME_TO_A_REAL_TOKEN")
SITE_TITLE = os.getenv("SITE_TITLE", "My Blog")
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")
CONTENT_DIR = Path(os.getenv("CONTENT_DIR", "./content"))
STATIC_DIR = Path(os.getenv("STATIC_DIR", "./static"))
THEMES_DIR = Path(os.getenv("THEMES_DIR", "./themes"))
ACTIVE_THEME = os.getenv("ACTIVE_THEME", "default")
DEPLOY_TARGET = os.getenv("DEPLOY_TARGET", "local")  # "local" or "github_pages"

# GitHub Pages deployment config
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")       # "username/repo"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "gh-pages")

# Detect cloud mode: no writable filesystem
CLOUD_MODE = bool(os.getenv("DATABASE_URL"))

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

db = None
builder = None
deployer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db, builder, deployer

    # --- Taxonomy DB ---
    db = get_taxonomy_db()
    await db.initialize()

    # In cloud mode, store Markdown source in a DB table too
    if CLOUD_MODE:
        await _ensure_source_table()

    # --- Build Pipeline ---
    # In cloud mode, we still build HTML — just don't write it to disk.
    # Instead we capture the HTML string and push it via deployer.
    from pipeline.builder_cloud import CloudBuildPipeline
    builder = CloudBuildPipeline(
        themes_dir=THEMES_DIR,
        active_theme=ACTIVE_THEME,
        site_title=SITE_TITLE,
        site_url=SITE_URL,
    )
    await builder.initialize()

    # --- Deployer ---
    if DEPLOY_TARGET == "github_pages" and GITHUB_TOKEN and GITHUB_REPO:
        from pipeline.deployer import GitHubPagesDeployer
        deployer = GitHubPagesDeployer(
            token=GITHUB_TOKEN,
            repo=GITHUB_REPO,
            branch=GITHUB_BRANCH,
        )
        await deployer.ensure_nojekyll()
        print(f"[deploy] GitHub Pages → {GITHUB_REPO}@{GITHUB_BRANCH}")
    else:
        deployer = None
        # Local mode: ensure directories exist
        CONTENT_DIR.mkdir(parents=True, exist_ok=True)
        STATIC_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[deploy] Local filesystem → {STATIC_DIR}")

    yield

    await db.close()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="note2cms",
    description="Past-Browser Publishing Protocol",
    version="0.2.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

async def verify_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if token != API_TOKEN:
        raise HTTPException(403, "Invalid token")
    return token


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class PublishRequest(BaseModel):
    markdown: str = Field(..., description="Full Markdown content including frontmatter")


class PublishResponse(BaseModel):
    permalink: str
    slug: str
    title: str
    created: bool


class PostSummary(BaseModel):
    slug: str
    title: str
    date: str
    tags: list[str]
    reading_time: int
    excerpt: str
    permalink: str


# ---------------------------------------------------------------------------
# Endpoint 1: POST /publish
# ---------------------------------------------------------------------------

@app.post("/publish", response_model=PublishResponse)
async def publish(req: PublishRequest, _token: str = Depends(verify_token)):
    """Push Markdown, get a permalink."""
    post = parse_markdown(req.markdown)

    # Check if this is new or an update
    existing = await db.get_post(post.slug)
    is_new = existing is None

    # Store source Markdown
    await _store_source(post.slug, req.markdown)

    # Build HTML
    post_html = builder.render_post(post)
    index_needs_rebuild = True

    # Pipeline 1: Deploy built HTML
    if deployer:
        await deployer.deploy_post(post.slug, post_html)
    else:
        post_dir = STATIC_DIR / post.slug
        post_dir.mkdir(parents=True, exist_ok=True)
        (post_dir / "index.html").write_text(post_html, encoding="utf-8")

    # Pipeline 2: Update taxonomy
    await db.upsert_post(post)

    # Rebuild index
    await _rebuild_index()

    permalink = f"{SITE_URL}/posts/{post.slug}/"
    return PublishResponse(
        permalink=permalink,
        slug=post.slug,
        title=post.title,
        created=is_new,
    )


# ---------------------------------------------------------------------------
# Endpoint 2: GET /posts/{slug}/source
# ---------------------------------------------------------------------------

@app.get("/posts/{slug}/source", response_class=PlainTextResponse)
async def get_source(slug: str, _token: str = Depends(verify_token)):
    """Get the original Markdown back. Edit it, push it again."""
    source = await _retrieve_source(slug)
    if source is None:
        raise HTTPException(404, f"Post '{slug}' not found")
    return source


# ---------------------------------------------------------------------------
# Endpoint 3: DELETE /posts/{slug}
# ---------------------------------------------------------------------------

@app.delete("/posts/{slug}")
async def delete_post(slug: str, _token: str = Depends(verify_token)):
    """Remove a post entirely."""
    source = await _retrieve_source(slug)
    if source is None:
        raise HTTPException(404, f"Post '{slug}' not found")

    # Remove source
    await _delete_source(slug)

    # Remove built output
    if deployer:
        await deployer.delete_post(slug)
    else:
        import shutil
        post_dir = STATIC_DIR / slug
        if post_dir.exists():
            shutil.rmtree(post_dir)

    # Remove from taxonomy
    await db.delete_post(slug)

    # Rebuild index
    await _rebuild_index()

    return {"status": "deleted", "slug": slug}


# ---------------------------------------------------------------------------
# Endpoint 4: GET /posts
# ---------------------------------------------------------------------------

@app.get("/posts", response_model=list[PostSummary])
async def list_posts():
    """List all posts — public, no auth needed."""
    posts = await db.list_posts()
    return [
        PostSummary(
            slug=p["slug"],
            title=p["title"],
            date=p["date"],
            tags=p["tags"],
            reading_time=p["reading_time"],
            excerpt=p["excerpt"],
            permalink=f"{SITE_URL}/posts/{p['slug']}/",
        )
        for p in posts
    ]


# ---------------------------------------------------------------------------
# Static file serving (local mode only)
# ---------------------------------------------------------------------------

if not CLOUD_MODE:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/posts", StaticFiles(directory=STATIC_DIR, html=True), name="blog")


# ---------------------------------------------------------------------------
# Index rebuild helper
# ---------------------------------------------------------------------------

async def _rebuild_index():
    """Rebuild the index page from current taxonomy."""
    posts = await db.list_posts()
    index_html = builder.render_index(posts)

    if deployer:
        await deployer.deploy_index(index_html)
    else:
        (STATIC_DIR / "index.html").write_text(index_html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Markdown source storage (DB in cloud, filesystem locally)
# ---------------------------------------------------------------------------

async def _ensure_source_table():
    """Create the markdown source table in PostgreSQL."""
    if hasattr(db, '_pool'):  # PostgreSQL
        async with db._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS markdown_source (
                    slug TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)


async def _store_source(slug: str, markdown: str):
    """Store raw Markdown — DB in cloud, filesystem locally."""
    if CLOUD_MODE and hasattr(db, '_pool'):
        async with db._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO markdown_source (slug, content, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (slug) DO UPDATE SET
                    content = EXCLUDED.content,
                    updated_at = NOW()
            """, slug, markdown)
    else:
        CONTENT_DIR.mkdir(parents=True, exist_ok=True)
        (CONTENT_DIR / f"{slug}.md").write_text(markdown, encoding="utf-8")


async def _retrieve_source(slug: str) -> Optional[str]:
    """Retrieve raw Markdown — DB in cloud, filesystem locally."""
    if CLOUD_MODE and hasattr(db, '_pool'):
        async with db._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT content FROM markdown_source WHERE slug = $1", slug
            )
            return row["content"] if row else None
    else:
        md_path = CONTENT_DIR / f"{slug}.md"
        if md_path.exists():
            return md_path.read_text(encoding="utf-8")
        return None


async def _delete_source(slug: str):
    """Delete raw Markdown — DB in cloud, filesystem locally."""
    if CLOUD_MODE and hasattr(db, '_pool'):
        async with db._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM markdown_source WHERE slug = $1", slug
            )
    else:
        md_path = CONTENT_DIR / f"{slug}.md"
        if md_path.exists():
            md_path.unlink()
