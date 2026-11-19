"""End-to-end API, GitHub Git Data batch deployer, and CLI client tests."""

import base64
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import api as api_module
from cli import n2c
from pipeline.deployer import DeployBatch, GitHubPagesDeployer


def _make_png_bytes(w: int = 1600, h: int = 1200) -> bytes:
    img = Image.new("RGB", (w, h), color=(40, 120, 200))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def configured_client(tmp_path, monkeypatch):
    content_dir = tmp_path / "content"
    static_dir = tmp_path / "static"
    db_path = tmp_path / "taxonomy.db"

    monkeypatch.setenv("API_TOKEN", "secret-test-token")
    monkeypatch.setenv("SITE_TITLE", "Test Notes")
    monkeypatch.setenv("SITE_URL", "http://testserver")
    monkeypatch.setenv("CONTENT_DIR", str(content_dir))
    monkeypatch.setenv("STATIC_DIR", str(static_dir))
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("ACTIVE_THEME", "default")
    monkeypatch.setenv("DEPLOY_TARGET", "local")
    monkeypatch.setenv("POSTS_PER_PAGE", "2")
    monkeypatch.setenv("PAGINATION_MODE", "stable")
    monkeypatch.setenv("SITE_LANG", "ru")
    monkeypatch.setenv("SEARCH", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)

    with TestClient(api_module.app) as client:
        yield client, content_dir, static_dir


def test_full_api_lifecycle_with_assets_pagination_tags_feeds_search(configured_client):
    client, content_dir, static_dir = configured_client
    headers = {"Authorization": "Bearer secret-test-token"}

    # Auth and validation checks
    r_bad_tok = client.post("/publish", json={"markdown": "# x"}, headers={"Authorization": "Bearer wrong"})
    assert r_bad_tok.status_code == 403

    r_no_title = client.post("/publish", json={"markdown": "Body without title"}, headers=headers)
    assert r_no_title.status_code == 422

    r_import = client.post("/import-from-blog", headers=headers)
    assert r_import.status_code == 400

    # 1. Publish static page About
    r_page = client.post(
        "/publish",
        json={"markdown": "---\ntitle: About\ntype: page\n---\n\nAuthor bio."},
        headers=headers,
    )
    assert r_page.status_code == 200

    # 2. Publish 3 posts with carousel images on post #3
    for i in (1, 2):
        r = client.post(
            "/publish",
            json={
                "markdown": (
                    f"---\ntitle: Post {i}\ndate: 2026-03-0{i}\ntags: [notes, python]\n"
                    f"series: My Series\nseries_order: {i}\n---\n\nText for post {i}."
                )
            },
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["created"] is True

    img_b64 = base64.b64encode(_make_png_bytes(1600, 1200)).decode("ascii")
    r3 = client.post(
        "/publish",
        json={
            "markdown": (
                "---\ntitle: Photo Hike\ndate: 2026-03-03\ntags: [travel, python]\n---\n\n"
                "![Peak 1](p1.png)\n![Peak 2](p2.png)\n\nGreat hike."
            ),
            "assets": {"p1.png": img_b64, "p2.png": img_b64},
        },
        headers=headers,
    )
    assert r3.status_code == 200
    assert sorted(r3.json()["assets_uploaded"]) == ["p1.png", "p2.png"]

    # Source returns original markdown with original filenames intact
    r_src = client.get("/posts/photo-hike/source", headers=headers)
    assert r_src.status_code == 200
    assert "![Peak 1](p1.png)" in r_src.text

    # Rendered HTML has carousel and zero scripts
    r_html = client.get("/posts/photo-hike/")
    assert r_html.status_code == 200
    assert 'class="n2c-carousel"' in r_html.text
    assert "<script" not in r_html.text.lower()

    # Post without images got generated OG card
    assert (static_dir / "assets" / "post-1" / "og.png").exists()

    # Pagination (per_page=2, stable mode, 3 posts -> page/1 has post 1&2, index has post 3)
    assert (static_dir / "page" / "1" / "index.html").exists()
    r_idx = client.get("/posts/")
    assert "Photo Hike" in r_idx.text
    assert "/posts/about/" in r_idx.text
    assert 'class="n2c-pagination"' in r_idx.text

    # API list & filtering
    r_list = client.get("/posts", params={"tag": "python", "limit": 2, "offset": 0})
    assert r_list.status_code == 200
    assert r_list.headers["X-Total-Count"] == "3"
    assert len(r_list.json()) == 2

    # Tags endpoint & static tag page
    r_tags = client.get("/tags")
    assert r_tags.status_code == 200
    tag_names = {t["name"]: t["count"] for t in r_tags.json()["tags"]}
    assert tag_names["python"] == 3
    assert client.get("/posts/tags/travel/").status_code == 200

    # Feeds, sitemap, robots, and search
    assert "<rss version=\"2.0\"" in client.get("/feed.xml").text
    assert "<feed xmlns=\"http://www.w3.org/2005/Atom\"" in client.get("/atom.xml").text
    assert "http://testserver/posts/photo-hike/" in client.get("/sitemap.xml").text
    assert "Sitemap: http://testserver/sitemap.xml" in client.get("/robots.txt").text
    assert client.get("/search-index.json").status_code == 200
    assert client.get("/posts/search/").status_code == 200

    r_search = client.get("/search", params={"q": "hike"})
    assert r_search.status_code == 200
    assert [p["slug"] for p in r_search.json()] == ["photo-hike"]

    # POST /media endpoint
    r_media = client.post(
        "/media",
        json={"slug": "post-1", "filename": "extra.png", "data": img_b64},
        headers=headers,
    )
    assert r_media.status_code == 200
    assert r_media.json()["width"] * r_media.json()["height"] <= 1_000_000

    # POST /rebuild
    r_reb = client.post("/rebuild", headers=headers)
    assert r_reb.status_code == 200
    assert r_reb.json()["posts"] == 4

    # DELETE /posts/{slug}
    r_del = client.delete("/posts/photo-hike", headers=headers)
    assert r_del.status_code == 200
    assert not (static_dir / "photo-hike").exists()
    assert not (static_dir / "assets" / "photo-hike").exists()


@pytest.mark.asyncio
async def test_github_pages_deployer_commits_batch_in_single_commit(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            calls.append(("GET", url))
            resp = MagicMock()
            resp.status_code = 200
            if url.endswith("/git/ref/heads/gh-pages"):
                resp.json.return_value = {"object": {"sha": "commit_0"}}
            elif url.endswith("/git/commits/commit_0"):
                resp.json.return_value = {"tree": {"sha": "tree_0"}}
            elif "/git/trees/" in url:
                resp.json.return_value = {"tree": [{"path": "posts/old/index.html", "type": "blob"}]}
            return resp

        async def post(self, url, json=None, **kwargs):
            calls.append(("POST", url, json))
            resp = MagicMock()
            resp.status_code = 201
            if url.endswith("/git/blobs"):
                resp.json.return_value = {"sha": "blob_bin"}
            elif url.endswith("/git/trees"):
                resp.json.return_value = {"sha": "tree_1"}
            elif url.endswith("/git/commits"):
                resp.json.return_value = {"sha": "commit_1"}
            return resp

        async def patch(self, url, json=None, **kwargs):
            calls.append(("PATCH", url, json))
            resp = MagicMock()
            resp.status_code = 200
            return resp

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    deployer = GitHubPagesDeployer(token="gh_tok", repo="user/blog", branch="gh-pages")
    batch = DeployBatch()
    batch.add("posts/a/index.html", "<h1>A</h1>")
    batch.add("posts/index.html", "<h1>Index</h1>")
    batch.add("posts/assets/a/pic.png", b"\x89PNG\r\n\x1a\n")
    batch.remove("posts/old/index.html")

    ok = await deployer.deploy_batch(batch, message="publish: a")
    assert ok is True

    post_trees = [c for c in calls if c[0] == "POST" and c[1].endswith("/git/trees")]
    post_commits = [c for c in calls if c[0] == "POST" and c[1].endswith("/git/commits")]
    patch_refs = [c for c in calls if c[0] == "PATCH" and "/git/refs/heads/" in c[1]]

    assert len(post_trees) == 1
    assert len(post_commits) == 1
    assert len(patch_refs) == 1
    tree_paths = {item["path"] for item in post_trees[0][2]["tree"]}
    assert tree_paths == {
        "posts/a/index.html",
        "posts/index.html",
        "posts/assets/a/pic.png",
        "posts/old/index.html",
    }


def test_cli_n2c_publish_writeback_sync_pull_delete(configured_client, tmp_path):
    client, _, _ = configured_client
    notes_dir = tmp_path / "vault"
    notes_dir.mkdir()
    img_file = notes_dir / "photo.png"
    img_file.write_bytes(_make_png_bytes(800, 600))

    note_file = notes_dir / "my-note.md"
    note_file.write_text(
        "---\ntitle: CLI Note\ntags: [cli]\n---\n\n![[photo.png|My Photo]]\n\nHello CLI.",
        encoding="utf-8",
    )

    # Publish with --write-back
    rc = n2c.main(
        ["--url", "http://testserver", "--token", "secret-test-token", "publish", str(note_file), "--write-back"],
        client=client,
    )
    assert rc == 0
    updated_text = note_file.read_text(encoding="utf-8")
    assert "slug: cli-note" in updated_text
    assert "permalink: http://testserver/posts/cli-note/" in updated_text

    # Pull source back
    pulled_file = notes_dir / "pulled.md"
    rc_pull = n2c.main(
        ["--url", "http://testserver", "--token", "secret-test-token", "pull", "cli-note", "-o", str(pulled_file)],
        client=client,
    )
    assert rc_pull == 0
    assert "Hello CLI." in pulled_file.read_text(encoding="utf-8")

    # Sync directory (pulled.md is new, my-note.md is also hashed first time)
    pulled_file.unlink()
    rc_sync1 = n2c.main(
        ["--url", "http://testserver", "--token", "secret-test-token", "sync", str(notes_dir)],
        client=client,
    )
    assert rc_sync1 == 0
    assert (notes_dir / ".n2c-sync.json").exists()

    # Second sync skips unchanged
    rc_sync2 = n2c.main(
        ["--url", "http://testserver", "--token", "secret-test-token", "sync", str(notes_dir)],
        client=client,
    )
    assert rc_sync2 == 0

    # List & delete
    assert n2c.main(["--url", "http://testserver", "list"], client=client) == 0
    assert n2c.main(
        ["--url", "http://testserver", "--token", "secret-test-token", "delete", "cli-note"],
        client=client,
    ) == 0


@pytest.mark.asyncio
async def test_local_build_pipeline_rebuild_all(tmp_path):
    from pipeline.builder import BuildPipeline

    content_dir = tmp_path / "content"
    static_dir = tmp_path / "static"
    themes_dir = Path(__file__).parent.parent / "themes"
    content_dir.mkdir()
    (content_dir / "first.md").write_text("---\ntitle: First\ndate: 2026-01-01\n---\nHello!", encoding="utf-8")
    (content_dir / "about.md").write_text("---\ntitle: About\ntype: page\n---\nBio!", encoding="utf-8")

    bp = BuildPipeline(
        content_dir=content_dir,
        static_dir=static_dir,
        themes_dir=themes_dir,
        active_theme="swiss",
        site_title="Local Site",
        site_url="http://localhost:8000",
    )
    await bp.initialize()
    await bp.rebuild_all()

    assert (static_dir / "first" / "index.html").exists()
    assert (static_dir / "about" / "index.html").exists()
    assert (static_dir / "index.html").exists()
    assert (static_dir / "assets" / "first" / "og.png").exists()


def test_pinned_post_pagination_tags_and_share_buttons(configured_client):
    client, _, _ = configured_client
    headers = {"Authorization": "Bearer secret-test-token"}

    # Static page must not show share bar
    r_about = client.post(
        "/publish",
        json={"markdown": "---\ntitle: About\ntype: page\npinned: true\n---\n\nBio."},
        headers=headers,
    )
    assert r_about.status_code == 200
    assert 'class="n2c-share-bar"' not in client.get("/posts/about/").text

    # Publish an older pinned post (2026-01-01) and two newer posts (2026-03-01, 2026-03-02)
    r_pin1 = client.post(
        "/publish",
        json={
            "markdown": (
                "---\ntitle: Start Here\ndate: 2026-01-01\ntags: [intro]\npinned: true\n---\n\n"
                "Welcome guide."
            )
        },
        headers=headers,
    )
    assert r_pin1.status_code == 200

    for idx in (1, 2):
        r = client.post(
            "/publish",
            json={
                "markdown": (
                    f"---\ntitle: Fresh {idx}\ndate: 2026-03-0{idx}\ntags: [news]\n---\n\nBody {idx}."
                )
            },
            headers=headers,
        )
        assert r.status_code == 200

    # Single post page has share bar with localized buttons and zero <script>
    post_html = client.get("/posts/fresh-1/").text
    assert 'class="n2c-share-bar"' in post_html
    assert "Поделиться" in post_html
    assert "Скопировать ссылку" in post_html
    assert "<script" not in post_html.lower()

    # Main index shows full pinned card AND keeps newest post on index without shifting stable page/1
    idx_html = client.get("/posts/").text
    assert 'class="n2c-pinned-card"' in idx_html
    assert "Закреплено" in idx_html
    assert "Start Here" in idx_html
    assert "Fresh 2" in idx_html

    # Archive page/1 shows compact pinned banner (not full card) + chronological older posts
    page1_html = client.get("/posts/page/1/").text
    assert 'class="n2c-pinned-compact"' in page1_html
    assert 'class="n2c-pinned-card"' not in page1_html
    assert "Start Here" in page1_html
    assert "Fresh 1" in page1_html

    # Tag page (even for a tag not on the pinned post) shows compact pinned banner
    tag_html = client.get("/posts/tags/news/").text
    assert 'class="n2c-pinned-compact"' in tag_html
    assert 'class="n2c-pinned-card"' not in tag_html
    assert "Start Here" in tag_html

    # API GET /posts exposes pinned flag while preserving chronological order
    posts_api = client.get("/posts").json()
    assert [(p["slug"], p["pinned"]) for p in posts_api] == [
        ("fresh-2", False),
        ("fresh-1", False),
        ("start-here", True),
    ]

    # Publishing a newer pinned post switches active pin everywhere
    r_pin2 = client.post(
        "/publish",
        json={
            "markdown": (
                "---\ntitle: Newer Pinned\ndate: 2026-04-01\ntags: [meta]\npinned: true\n---\n\n"
                "Updated announcement."
            )
        },
        headers=headers,
    )
    assert r_pin2.status_code == 200
    assert "Newer Pinned" in client.get("/posts/").text
    assert "Newer Pinned" in client.get("/posts/page/1/").text
    assert "Newer Pinned" in client.get("/posts/tags/news/").text

    # Unpinning newer-pinned falls back to the remaining older pinned post
    r_unpin = client.post(
        "/publish",
        json={
            "markdown": (
                "---\ntitle: Newer Pinned\nslug: newer-pinned\ndate: 2026-04-01\n"
                "tags: [meta]\npinned: false\n---\n\nUpdated announcement."
            )
        },
        headers=headers,
    )
    assert r_unpin.status_code == 200
    assert "Start Here" in client.get("/posts/").text
    assert "Start Here" in client.get("/posts/tags/news/").text

    # Deleting the remaining pinned post removes pinned block everywhere
    r_del = client.delete("/posts/start-here", headers=headers)
    assert r_del.status_code == 200
    assert 'class="n2c-pinned-card"' not in client.get("/posts/").text
    assert 'class="n2c-pinned-compact"' not in client.get("/posts/tags/news/").text


@pytest.mark.asyncio
async def test_sqlite_migration_adds_pinned_column(tmp_path):
    import aiosqlite
    from pipeline.parser import parse_markdown
    from pipeline.taxonomy import TaxonomyDB

    db_path = tmp_path / "legacy.db"
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("""
            CREATE TABLE posts (
                slug TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                date TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                reading_time INTEGER NOT NULL DEFAULT 1,
                excerpt TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await conn.commit()

    db = TaxonomyDB(str(db_path))
    await db.initialize()
    post = parse_markdown("---\ntitle: Migrated Pin\npinned: true\n---\nBody.")
    await db.upsert_post(post)
    loaded = await db.get_post("migrated-pin")
    assert loaded is not None
    assert loaded["pinned"] is True
    await db.close()


def test_migrator_recovers_pinned_meta(monkeypatch):
    from pipeline.migrator import fetch_and_parse_post

    sample_html = """<!DOCTYPE html><html><head>
    <meta property="og:title" content="Pinned Recovery">
    <meta name="description" content="Recovered excerpt">
    <meta name="n2c:pinned" content="true">
    </head><body><article><header><time datetime="2026-03-16T00:00:00+00:00">March 16, 2026</time></header>
    <div class="post-content"><p>Hello world.</p></div></article></body></html>"""

    class FakeResp:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return sample_html.encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=15: FakeResp())
    data = fetch_and_parse_post("user/blog", slug="pinned-recovery")
    assert data["pinned"] is True
    assert "pinned: true" in data["markdown"]


