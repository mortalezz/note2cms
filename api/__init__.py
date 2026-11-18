"""
note2cms — Past-Browser Publishing Protocol
Minimal API for publishing Markdown notes to static HTML.

Deployment modes:
  LOCAL:  SQLite taxonomy + local filesystem for content/static
  CLOUD:  PostgreSQL taxonomy + GitHub Pages for static output
          (Markdown source stored in DB, single-commit Git Data API deploys)
"""

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from pipeline.builder_cloud import CloudBuildPipeline
from pipeline.deployer import DeployBatch, GitHubPagesDeployer, LocalDeployer
from pipeline.feeds import render_atom, render_robots, render_rss, render_sitemap
from pipeline.markdown_ext import render_markdown
from pipeline.media import ProcessedAsset, decode_base64_asset, process_image
from pipeline.paginator import paginate_posts, select_incremental_slices
from pipeline.parser import parse_markdown
from pipeline.search import build_search_index, search_posts
from pipeline.source_store import SourceStore, get_source_store
from pipeline.taxonomy_pg import get_taxonomy_db


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _load_settings() -> dict:
    cors_raw = os.getenv("CORS_ORIGINS", "*")
    cors_origins = [o.strip() for o in cors_raw.split(",") if o.strip()] or ["*"]
    nav_raw = os.getenv("NAV_PAGES", "")
    nav_pages = [s.strip() for s in nav_raw.split(",") if s.strip()]
    return {
        "API_TOKEN": os.getenv("API_TOKEN", "CHANGE_ME_TO_A_REAL_TOKEN"),
        "SITE_TITLE": os.getenv("SITE_TITLE", "My Blog"),
        "SITE_URL": os.getenv("SITE_URL", "http://localhost:8000").rstrip("/"),
        "CONTENT_DIR": Path(os.getenv("CONTENT_DIR", "./content")),
        "STATIC_DIR": Path(os.getenv("STATIC_DIR", "./static")),
        "THEMES_DIR": Path(os.getenv("THEMES_DIR", "./themes")),
        "ACTIVE_THEME": os.getenv("ACTIVE_THEME", "default"),
        "DEPLOY_TARGET": os.getenv("DEPLOY_TARGET", "local"),
        "GITHUB_TOKEN": os.getenv("GITHUB_TOKEN", ""),
        "GITHUB_REPO": os.getenv("GITHUB_REPO", ""),
        "GITHUB_BRANCH": os.getenv("GITHUB_BRANCH", "gh-pages"),
        "CLOUD_MODE": bool(os.getenv("DATABASE_URL")),
        "POSTS_PER_PAGE": max(1, int(os.getenv("POSTS_PER_PAGE", "10"))),
        "PAGINATION_MODE": os.getenv("PAGINATION_MODE", "stable").strip().lower(),
        "GALLERY_AUTO": os.getenv("GALLERY_AUTO", "true").strip().lower() not in ("false", "0", "no"),
        "MAX_IMAGE_MP": float(os.getenv("MAX_IMAGE_MP", "1.0")),
        "MAX_ASSET_MB": float(os.getenv("MAX_ASSET_MB", "15.0")),
        "SITE_LANG": os.getenv("SITE_LANG", "en"),
        "FEED_FULL_TEXT": os.getenv("FEED_FULL_TEXT", "true").strip().lower() not in ("false", "0", "no"),
        "SEARCH_ENABLED": os.getenv("SEARCH", "false").strip().lower() in ("true", "1", "yes"),
        "CORS_ORIGINS": cors_origins,
        "NAV_PAGES": nav_pages,
    }


SETTINGS = _load_settings()

# Module-level state initialized during lifespan
db = None
source_store: Optional[SourceStore] = None
builder: Optional[CloudBuildPipeline] = None
deployer = None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global SETTINGS, db, source_store, builder, deployer
    SETTINGS = _load_settings()

    # --- Taxonomy DB ---
    db = get_taxonomy_db()
    await db.initialize()

    # --- Markdown Source Store ---
    source_store = get_source_store(db, SETTINGS["CONTENT_DIR"], SETTINGS["CLOUD_MODE"])
    await source_store.initialize()

    # --- Unified Jinja2 Build Pipeline ---
    builder = CloudBuildPipeline(
        themes_dir=SETTINGS["THEMES_DIR"],
        active_theme=SETTINGS["ACTIVE_THEME"],
        site_title=SETTINGS["SITE_TITLE"],
        site_url=SETTINGS["SITE_URL"],
        site_lang=SETTINGS["SITE_LANG"],
        enable_carousel=SETTINGS["GALLERY_AUTO"],
        search_enabled=SETTINGS["SEARCH_ENABLED"],
    )
    await builder.initialize()

    # --- Deployer ---
    if (
        SETTINGS["DEPLOY_TARGET"] == "github_pages"
        and SETTINGS["GITHUB_TOKEN"]
        and SETTINGS["GITHUB_REPO"]
    ):
        deployer = GitHubPagesDeployer(
            token=SETTINGS["GITHUB_TOKEN"],
            repo=SETTINGS["GITHUB_REPO"],
            branch=SETTINGS["GITHUB_BRANCH"],
        )
        await deployer.ensure_nojekyll()
        print(f"[deploy] GitHub Pages -> {SETTINGS['GITHUB_REPO']}@{SETTINGS['GITHUB_BRANCH']}")
    else:
        SETTINGS["CONTENT_DIR"].mkdir(parents=True, exist_ok=True)
        SETTINGS["STATIC_DIR"].mkdir(parents=True, exist_ok=True)
        deployer = LocalDeployer(SETTINGS["STATIC_DIR"])
        print(f"[deploy] Local filesystem -> {SETTINGS['STATIC_DIR']}")

    # Refresh local static mount if not in cloud mode
    if not SETTINGS["CLOUD_MODE"]:
        app.router.routes[:] = [
            r for r in app.router.routes if getattr(r, "name", None) != "blog"
        ]
        app.mount(
            "/posts",
            StaticFiles(directory=SETTINGS["STATIC_DIR"], html=True),
            name="blog",
        )

    yield

    await db.close()


# ---------------------------------------------------------------------------
# App & Middleware
# ---------------------------------------------------------------------------

app = FastAPI(
    title="note2cms",
    description="Past-Browser Publishing Protocol",
    version="0.3.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS["CORS_ORIGINS"],
    allow_credentials=(SETTINGS["CORS_ORIGINS"] != ["*"]),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

async def verify_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    expected = SETTINGS["API_TOKEN"]
    if not secrets.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(403, "Invalid token")
    return token


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class PublishRequest(BaseModel):
    markdown: str = Field(..., description="Full Markdown content including frontmatter")
    assets: Optional[dict[str, str]] = Field(
        default=None,
        description="Optional mapping of local filename -> base64-encoded image bytes",
    )


class PublishResponse(BaseModel):
    permalink: str
    slug: str
    title: str
    created: bool
    assets_uploaded: list[str] = Field(default_factory=list)


class PostSummary(BaseModel):
    slug: str
    title: str
    date: str
    tags: list[str]
    reading_time: int
    excerpt: str
    permalink: str
    pinned: bool = False


class MediaUploadRequest(BaseModel):
    slug: str
    filename: str
    data: str


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _assets_map_from_meta(meta: dict) -> dict[str, ProcessedAsset]:
    out: dict[str, ProcessedAsset] = {}
    for orig_name, info in (meta or {}).items():
        if not isinstance(info, dict):
            continue
        out[orig_name] = ProcessedAsset(
            original_name=orig_name,
            primary_path=info.get("primary_path", ""),
            primary_url=info.get("primary_url", ""),
            width=int(info.get("width", 0)),
            height=int(info.get("height", 0)),
            srcset=info.get("srcset", ""),
            files={},
        )
    return out


def _assets_meta_from_map(assets_map: dict[str, ProcessedAsset]) -> dict[str, dict]:
    return {
        k: {
            "primary_path": v.primary_path,
            "primary_url": v.primary_url,
            "width": v.width,
            "height": v.height,
            "srcset": v.srcset,
        }
        for k, v in assets_map.items()
    }


def _find_active_pinned(posts: list[dict]) -> Optional[dict]:
    """Return the newest pinned post from a newest-first post list."""
    return next((p for p in posts if p.get("pinned")), None)


def _build_nav_pages(pages: list[dict]) -> list[dict]:
    site_url = SETTINGS["SITE_URL"]
    by_slug = {p["slug"]: p for p in pages}
    configured = SETTINGS["NAV_PAGES"]
    ordered: list[dict]
    if configured:
        ordered = [by_slug[s] for s in configured if s in by_slug]
    else:
        ordered = pages
    return [
        {
            "slug": p["slug"],
            "title": p["title"],
            "permalink": f"{site_url}/posts/{p['slug']}/",
        }
        for p in ordered
    ]


async def _render_stored_post_into_batch(
    slug: str,
    batch: DeployBatch,
    all_posts: list[dict],
    nav_pages: list[dict],
) -> None:
    raw_src = await source_store.get(slug)
    if raw_src is None:
        return
    try:
        parsed = parse_markdown(raw_src)
    except ValueError:
        return
    meta_row = await db.get_post(slug)
    assets_map = _assets_map_from_meta(meta_row.get("assets_meta", {}) if meta_row else {})
    rel = (
        builder.compute_post_relations(slug, all_posts, tags=parsed.tags, series_name=parsed.series)
        if parsed.post_type == "post"
        else {"prev_post": None, "next_post": None, "related_posts": [], "series_info": None}
    )
    bundle = builder.render_post_bundle(
        parsed,
        assets_map=assets_map,
        nav_pages=nav_pages,
        generate_og_card=False,
        **rel,
    )
    batch.add(f"posts/{slug}/index.html", bundle.html)


async def _add_site_artifacts(
    batch: DeployBatch,
    all_posts: list[dict],
    pages: list[dict],
    all_tags: dict[str, int],
    nav_pages: list[dict],
    current_body: Optional[tuple[str, str]] = None,
) -> None:
    """Populate RSS, Atom, sitemap, robots, and optional search index into DeployBatch."""
    site_title = SETTINGS["SITE_TITLE"]
    site_url = SETTINGS["SITE_URL"]
    lang = SETTINGS["SITE_LANG"]
    full_text = SETTINGS["FEED_FULL_TEXT"]

    rendered_bodies: dict[str, str] = {}
    if current_body:
        rendered_bodies[current_body[0]] = current_body[1]

    feed_posts = all_posts[:30]
    sources_map: dict[str, str] = {}
    if full_text or SETTINGS["SEARCH_ENABLED"]:
        for p in all_posts:
            s = p["slug"]
            if full_text and len(rendered_bodies) < 30 and s not in rendered_bodies and p in feed_posts:
                src = await source_store.get(s)
                if src is not None:
                    sources_map[s] = src
                    try:
                        parsed = parse_markdown(src)
                        assets_map = _assets_map_from_meta(p.get("assets_meta", {}))
                        rendered_bodies[s] = render_markdown(
                            parsed.content,
                            assets_map=assets_map,
                            enable_carousel=SETTINGS["GALLERY_AUTO"] and parsed.carousel,
                            lang=lang,
                        ).html
                    except ValueError:
                        pass
            elif SETTINGS["SEARCH_ENABLED"] and s not in sources_map:
                src = await source_store.get(s)
                if src is not None:
                    sources_map[s] = src

    batch.add(
        "feed.xml",
        render_rss(
            all_posts,
            site_title=site_title,
            site_url=site_url,
            lang=lang,
            full_text=full_text,
            rendered_bodies=rendered_bodies,
        ),
    )
    batch.add(
        "atom.xml",
        render_atom(
            all_posts,
            site_title=site_title,
            site_url=site_url,
            full_text=full_text,
            rendered_bodies=rendered_bodies,
        ),
    )
    batch.add(
        "sitemap.xml",
        render_sitemap(all_posts, pages, list(all_tags.keys()), site_url),
    )
    batch.add("robots.txt", render_robots(site_url))

    if SETTINGS["SEARCH_ENABLED"]:
        batch.add("search-index.json", build_search_index(all_posts, sources_map, site_url))
        batch.add("posts/search/index.html", builder.render_search_page(nav_pages=nav_pages))


async def _add_tag_pages(
    batch: DeployBatch,
    tags_to_build: set[str],
    all_tags: dict[str, int],
    nav_pages: list[dict],
    pinned_post: Optional[dict] = None,
) -> None:
    per_page = SETTINGS["POSTS_PER_PAGE"]
    mode = SETTINGS["PAGINATION_MODE"]

    batch.add("posts/tags/index.html", builder.render_tags_overview(all_tags, nav_pages=nav_pages))
    for tag in sorted(tags_to_build):
        tag_posts = await db.list_by_tag(tag)
        if not tag_posts:
            batch.remove_prefix(f"posts/tags/{tag}/")
            continue
        rendered_pages = builder.render_paginated_index(
            tag_posts,
            per_page=per_page,
            mode=mode,
            prefix=f"/posts/tags/{tag}",
            include_root_index=False,
            nav_pages=nav_pages,
            active_tag=tag,
            pinned_post=pinned_post,
        )
        for out_path, html_out in rendered_pages.items():
            batch.add(out_path, html_out)


# ---------------------------------------------------------------------------
# Endpoint 1: POST /publish
# ---------------------------------------------------------------------------

@app.post("/publish", response_model=PublishResponse)
async def publish(req: PublishRequest, _token: str = Depends(verify_token)):
    """Push Markdown (and optional base64 assets), get a permalink."""
    raw_markdown = req.markdown
    if "\x00" in raw_markdown:
        print("[publish] Warning: stripped NUL bytes from markdown")
        raw_markdown = raw_markdown.replace("\x00", "")

    try:
        post = parse_markdown(raw_markdown)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc

    existing = await db.get_post(post.slug)
    is_new = existing is None
    old_tags = set(existing.get("tags", [])) if existing else set()
    old_posts = await db.list_posts(include_pages=False)
    old_pinned = _find_active_pinned(old_posts)
    old_pinned_slug = old_pinned["slug"] if old_pinned else None
    old_rel = (
        builder.compute_post_relations(
            post.slug, old_posts, series_name=existing.get("series") or None
        )
        if existing
        else {"prev_post": None, "next_post": None, "series_info": None}
    )

    batch = DeployBatch()

    # Merge any previously stored asset metadata with newly uploaded assets
    assets_map = _assets_map_from_meta(existing.get("assets_meta", {}) if existing else {})
    uploaded_names: list[str] = []
    for filename, b64_data in (req.assets or {}).items():
        try:
            raw_bytes = decode_base64_asset(b64_data)
            asset = process_image(
                raw_bytes,
                filename,
                post.slug,
                site_url=SETTINGS["SITE_URL"],
                max_mp=SETTINGS["MAX_IMAGE_MP"],
                max_asset_mb=SETTINGS["MAX_ASSET_MB"],
            )
        except Exception as exc:
            raise HTTPException(422, detail=f"Invalid asset '{filename}': {exc}") from exc
        assets_map[filename] = asset
        uploaded_names.append(filename)
        for f_path, f_bytes in asset.files.items():
            batch.add(f_path, f_bytes)

    assets_meta = _assets_meta_from_map(assets_map)

    # Store source Markdown & update taxonomy
    await source_store.put(post.slug, raw_markdown)
    await db.upsert_post(post, assets_meta=assets_meta)

    # Updated state
    all_posts = await db.list_posts(include_pages=False)
    pages = await db.list_pages()
    nav_pages = _build_nav_pages(pages)
    all_tags = await db.list_all_tags()
    active_pinned = _find_active_pinned(all_posts)
    new_pinned_slug = active_pinned["slug"] if active_pinned else None
    pinned_changed = (old_pinned_slug != new_pinned_slug) or (new_pinned_slug == post.slug)

    # Render current post/page
    rel = (
        builder.compute_post_relations(
            post.slug, all_posts, tags=post.tags, series_name=post.series
        )
        if post.post_type == "post"
        else {"prev_post": None, "next_post": None, "related_posts": [], "series_info": None}
    )
    bundle = builder.render_post_bundle(
        post,
        assets_map=assets_map,
        nav_pages=nav_pages,
        generate_og_card=(post.post_type == "post"),
        **rel,
    )
    batch.add(f"posts/{post.slug}/index.html", bundle.html)
    if bundle.og_png_bytes:
        batch.add(f"posts/assets/{post.slug}/og.png", bundle.og_png_bytes)

    # Re-render affected neighbor & series posts so prev/next/series links stay current
    affected_slugs: set[str] = set()
    for neighbor in (
        rel.get("prev_post"),
        rel.get("next_post"),
        old_rel.get("prev_post"),
        old_rel.get("next_post"),
    ):
        if neighbor and neighbor.get("slug") != post.slug:
            affected_slugs.add(neighbor["slug"])
    if rel.get("series_info"):
        for item in rel["series_info"]["posts"]:
            if item["slug"] != post.slug:
                affected_slugs.add(item["slug"])

    for n_slug in sorted(affected_slugs):
        await _render_stored_post_into_batch(n_slug, batch, all_posts, nav_pages)

    # Incremental paginated index & tag pages
    per_page = SETTINGS["POSTS_PER_PAGE"]
    mode = SETTINGS["PAGINATION_MODE"]
    if post.post_type == "post":
        all_slices = paginate_posts(
            all_posts,
            per_page=per_page,
            mode=mode,
            base_url=SETTINGS["SITE_URL"],
            prefix="/posts",
        )
        is_new_newest = is_new and bool(all_posts) and all_posts[0]["slug"] == post.slug
        if pinned_changed:
            slices_to_build = all_slices
            tags_to_build = set(all_tags.keys()) | old_tags
        else:
            slices_to_build = select_incremental_slices(
                all_slices,
                mode=mode,
                per_page=per_page,
                is_new_newest=is_new_newest,
                changed_slug=post.slug,
                total_after=len(all_posts),
            )
            tags_to_build = set(post.tags) | old_tags
        for sl in slices_to_build:
            html_out = builder.render_index_slice(sl, nav_pages=nav_pages, pinned_post=active_pinned)
            for out_path in sl.output_paths:
                batch.add(out_path, html_out)

        await _add_tag_pages(batch, tags_to_build, all_tags, nav_pages, pinned_post=active_pinned)
    else:
        # Static page added/updated: update main index nav bar
        all_slices = paginate_posts(
            all_posts,
            per_page=per_page,
            mode=mode,
            base_url=SETTINGS["SITE_URL"],
            prefix="/posts",
        )
        for sl in all_slices:
            html_out = builder.render_index_slice(sl, nav_pages=nav_pages, pinned_post=active_pinned)
            for out_path in sl.output_paths:
                batch.add(out_path, html_out)

    await _add_site_artifacts(
        batch,
        all_posts,
        pages,
        all_tags,
        nav_pages,
        current_body=(post.slug, bundle.body_html) if post.post_type == "post" else None,
    )

    ok = await deployer.deploy_batch(batch, message=f"publish: {post.slug}")
    if not ok:
        raise HTTPException(502, "Failed to deploy static artifacts")

    permalink = f"{SETTINGS['SITE_URL']}/posts/{post.slug}/"
    return PublishResponse(
        permalink=permalink,
        slug=post.slug,
        title=post.title,
        created=is_new,
        assets_uploaded=uploaded_names,
    )


# ---------------------------------------------------------------------------
# Endpoint 2: GET /posts/{slug}/source
# ---------------------------------------------------------------------------

@app.get("/posts/{slug}/source", response_class=PlainTextResponse)
async def get_source(slug: str, _token: str = Depends(verify_token)):
    """Get the original Markdown back. Edit it, push it again."""
    source = await source_store.get(slug)
    if source is None:
        raise HTTPException(404, f"Post '{slug}' not found")
    return source


# ---------------------------------------------------------------------------
# Endpoint 3: DELETE /posts/{slug}
# ---------------------------------------------------------------------------

@app.delete("/posts/{slug}")
async def delete_post(slug: str, _token: str = Depends(verify_token)):
    """Remove a post, its assets, and rebuild affected index/tag/neighbor pages."""
    existing = await db.get_post(slug)
    if existing is None:
        raise HTTPException(404, f"Post '{slug}' not found")

    old_tags = set(existing.get("tags", []))
    old_posts = await db.list_posts(include_pages=False)
    old_rel = builder.compute_post_relations(
        slug, old_posts, series_name=existing.get("series") or None
    )

    await source_store.delete(slug)
    await db.delete_post(slug)

    batch = DeployBatch()
    batch.remove(f"posts/{slug}/index.html")
    batch.remove_prefix(f"posts/assets/{slug}/")

    all_posts = await db.list_posts(include_pages=False)
    pages = await db.list_pages()
    nav_pages = _build_nav_pages(pages)
    all_tags = await db.list_all_tags()
    active_pinned = _find_active_pinned(all_posts)

    # Re-render old neighbors / series peers
    affected_slugs: set[str] = set()
    for neighbor in (old_rel.get("prev_post"), old_rel.get("next_post")):
        if neighbor and neighbor.get("slug") != slug:
            affected_slugs.add(neighbor["slug"])
    if old_rel.get("series_info"):
        for item in old_rel["series_info"]["posts"]:
            if item["slug"] != slug:
                affected_slugs.add(item["slug"])
    for n_slug in sorted(affected_slugs):
        await _render_stored_post_into_batch(n_slug, batch, all_posts, nav_pages)

    # Rebuild paginated index
    for out_path, html_out in builder.render_paginated_index(
        all_posts,
        per_page=SETTINGS["POSTS_PER_PAGE"],
        mode=SETTINGS["PAGINATION_MODE"],
        nav_pages=nav_pages,
        pinned_post=active_pinned,
    ).items():
        batch.add(out_path, html_out)

    tags_to_rebuild = (set(all_tags.keys()) | old_tags) if existing.get("pinned") else old_tags
    await _add_tag_pages(batch, tags_to_rebuild, all_tags, nav_pages, pinned_post=active_pinned)
    await _add_site_artifacts(batch, all_posts, pages, all_tags, nav_pages)

    ok = await deployer.deploy_batch(batch, message=f"delete: {slug}")
    if not ok:
        raise HTTPException(502, "Failed to apply delete batch")

    return {"status": "deleted", "slug": slug}


# ---------------------------------------------------------------------------
# Endpoint 4: GET /posts, GET /tags, GET /search
# ---------------------------------------------------------------------------

@app.get("/posts", response_model=list[PostSummary])
async def list_posts(
    response: Response,
    tag: Optional[str] = Query(default=None, description="Filter by tag"),
    limit: Optional[int] = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    include_pages: bool = Query(default=False),
):
    """List posts with optional tag filter and offset/limit pagination — public."""
    if tag:
        posts = await db.list_by_tag(tag)
    else:
        posts = await db.list_posts(include_pages=include_pages)

    total = len(posts)
    response.headers["X-Total-Count"] = str(total)
    sliced = posts[offset:offset + limit] if limit is not None else posts[offset:]
    site_url = SETTINGS["SITE_URL"]

    return [
        PostSummary(
            slug=p["slug"],
            title=p["title"],
            date=p["date"],
            tags=p["tags"],
            reading_time=p["reading_time"],
            excerpt=p["excerpt"],
            permalink=f"{site_url}/posts/{p['slug']}/",
            pinned=bool(p.get("pinned", False)),
        )
        for p in sliced
    ]


@app.get("/tags")
async def list_tags():
    """List all tags with post counts — public."""
    counts = await db.list_all_tags()
    site_url = SETTINGS["SITE_URL"]
    return {
        "tags": [
            {"name": tag, "count": count, "url": f"{site_url}/posts/tags/{tag}/"}
            for tag, count in counts.items()
        ]
    }


@app.get("/search", response_model=list[PostSummary])
async def search_endpoint(q: str = Query(..., min_length=1)):
    """Search published posts by title, tags, excerpt, and body — public."""
    all_posts = await db.list_posts(include_pages=False)
    sources_map: dict[str, str] = {}
    for p in all_posts:
        src = await source_store.get(p["slug"])
        if src is not None:
            sources_map[p["slug"]] = src
    matches = search_posts(all_posts, q, sources=sources_map)
    site_url = SETTINGS["SITE_URL"]
    return [
        PostSummary(
            slug=p["slug"],
            title=p["title"],
            date=p["date"],
            tags=p["tags"],
            reading_time=p["reading_time"],
            excerpt=p["excerpt"],
            permalink=f"{site_url}/posts/{p['slug']}/",
            pinned=bool(p.get("pinned", False)),
        )
        for p in matches
    ]


# ---------------------------------------------------------------------------
# Media Upload: POST /media
# ---------------------------------------------------------------------------

@app.post("/media")
async def upload_media(request: Request, _token: str = Depends(verify_token)):
    """Upload and sanitize/resize a single media asset (JSON base64 or multipart)."""
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        slug = str(form.get("slug") or "").strip()
        file_obj = form.get("file")
        if not slug or file_obj is None:
            raise HTTPException(422, "Multipart upload requires 'slug' and 'file'")
        filename = str(form.get("filename") or getattr(file_obj, "filename", "image.jpg"))
        raw_bytes = await file_obj.read()
    else:
        body = await request.json()
        try:
            req = MediaUploadRequest(**body)
            raw_bytes = decode_base64_asset(req.data)
            slug = req.slug
            filename = req.filename
        except Exception as exc:
            raise HTTPException(422, detail=f"Invalid media payload: {exc}") from exc

    try:
        asset = process_image(
            raw_bytes,
            filename,
            slug,
            site_url=SETTINGS["SITE_URL"],
            max_mp=SETTINGS["MAX_IMAGE_MP"],
            max_asset_mb=SETTINGS["MAX_ASSET_MB"],
        )
    except Exception as exc:
        raise HTTPException(422, detail=str(exc)) from exc

    batch = DeployBatch()
    for f_path, f_bytes in asset.files.items():
        batch.add(f_path, f_bytes)

    ok = await deployer.deploy_batch(batch, message=f"media: {slug}/{filename}")
    if not ok:
        raise HTTPException(502, "Failed to deploy media asset")

    return {
        "filename": asset.original_name,
        "url": asset.primary_url,
        "path": asset.primary_path,
        "width": asset.width,
        "height": asset.height,
        "srcset": asset.srcset,
    }


# ---------------------------------------------------------------------------
# Bonus: POST /rebuild — re-render all posts with current theme in 1 commit
# ---------------------------------------------------------------------------

@app.post("/rebuild")
async def rebuild_all(_token: str = Depends(verify_token)):
    """Re-render every post, page, tag archive, feed, and index with the current theme."""
    all_items = await db.list_posts(include_pages=True)
    all_posts = await db.list_posts(include_pages=False)
    pages = await db.list_pages()
    nav_pages = _build_nav_pages(pages)
    all_tags = await db.list_all_tags()

    batch = DeployBatch()
    rebuilt = 0

    for row in all_items:
        source = await source_store.get(row["slug"])
        if source is None:
            continue
        post = parse_markdown(source)
        assets_map = _assets_map_from_meta(row.get("assets_meta", {}))
        rel = (
            builder.compute_post_relations(
                post.slug, all_posts, tags=post.tags, series_name=post.series
            )
            if post.post_type == "post"
            else {"prev_post": None, "next_post": None, "related_posts": [], "series_info": None}
        )
        bundle = builder.render_post_bundle(
            post,
            assets_map=assets_map,
            nav_pages=nav_pages,
            generate_og_card=(post.post_type == "post"),
            **rel,
        )
        batch.add(f"posts/{post.slug}/index.html", bundle.html)
        if bundle.og_png_bytes:
            batch.add(f"posts/assets/{post.slug}/og.png", bundle.og_png_bytes)
        rebuilt += 1

    active_pinned = _find_active_pinned(all_posts)
    for out_path, html_out in builder.render_paginated_index(
        all_posts,
        per_page=SETTINGS["POSTS_PER_PAGE"],
        mode=SETTINGS["PAGINATION_MODE"],
        nav_pages=nav_pages,
        pinned_post=active_pinned,
    ).items():
        batch.add(out_path, html_out)

    await _add_tag_pages(batch, set(all_tags.keys()), all_tags, nav_pages, pinned_post=active_pinned)
    await _add_site_artifacts(batch, all_posts, pages, all_tags, nav_pages)

    ok = await deployer.deploy_batch(batch, message="rebuild all")
    if not ok:
        raise HTTPException(502, "Failed to deploy rebuild batch")

    return {"status": "rebuilt", "posts": rebuilt}


# ---------------------------------------------------------------------------
# Migration: POST /import-from-blog
# ---------------------------------------------------------------------------

@app.post("/import-from-blog")
async def import_from_blog(_token: str = Depends(verify_token)):
    """Recover published posts from configured GITHUB_REPO into this database."""
    repo = SETTINGS["GITHUB_REPO"]
    if not repo:
        raise HTTPException(400, "GITHUB_REPO is not configured")

    from pipeline.migrator import fetch_and_parse_post, get_post_slugs

    branch = SETTINGS["GITHUB_BRANCH"] or "gh-pages"
    slugs = get_post_slugs(repo, branch, SETTINGS["GITHUB_TOKEN"] or None)
    imported = 0

    for slug in slugs:
        post_data = fetch_and_parse_post(repo, branch, slug, SETTINGS["GITHUB_TOKEN"] or None)
        post = parse_markdown(post_data["markdown"])
        await source_store.put(post.slug, post_data["markdown"])
        await db.upsert_post(post)
        imported += 1

    return {"status": "ok", "imported": imported, "repo": repo}


# ---------------------------------------------------------------------------
# Local root static routes (feeds, sitemap, robots, root index)
# ---------------------------------------------------------------------------

def _serve_local_static(filename: str, media_type: Optional[str] = None):
    if SETTINGS["CLOUD_MODE"]:
        raise HTTPException(404, "Not available in cloud mode")
    target = SETTINGS["STATIC_DIR"] / filename
    if not target.exists():
        raise HTTPException(404, f"{filename} not built yet")
    return FileResponse(target, media_type=media_type)


@app.get("/")
async def local_root():
    return _serve_local_static("index.html", "text/html")


@app.get("/feed.xml")
async def local_rss():
    return _serve_local_static("feed.xml", "application/rss+xml")


@app.get("/atom.xml")
async def local_atom():
    return _serve_local_static("atom.xml", "application/atom+xml")


@app.get("/sitemap.xml")
async def local_sitemap():
    return _serve_local_static("sitemap.xml", "application/xml")


@app.get("/robots.txt")
async def local_robots():
    return _serve_local_static("robots.txt", "text/plain")


@app.get("/search-index.json")
async def local_search_index():
    return _serve_local_static("search-index.json", "application/json")
