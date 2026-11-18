"""
Taxonomy pipeline — SQLite-backed post index.

This is a derived data store. The Markdown files are the system of record.
This DB exists for fast queries and to feed the Index.jsx template.
You could delete it and rebuild from the content directory at any time.
"""

import json
import aiosqlite
from typing import Optional


class TaxonomyDB:
    def __init__(self, db_path: str = "./taxonomy.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        """Create the database and table if they don't exist, and run safe migrations."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                slug TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                date TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                reading_time INTEGER NOT NULL DEFAULT 1,
                excerpt TEXT NOT NULL DEFAULT '',
                cover TEXT NOT NULL DEFAULT '',
                series TEXT NOT NULL DEFAULT '',
                series_order INTEGER,
                post_type TEXT NOT NULL DEFAULT 'post',
                assets_meta TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Migrate existing databases safely
        cursor = await self._db.execute("PRAGMA table_info(posts)")
        existing_cols = {row[1] for row in await cursor.fetchall()}
        migrations = [
            ("cover", "ALTER TABLE posts ADD COLUMN cover TEXT NOT NULL DEFAULT ''"),
            ("series", "ALTER TABLE posts ADD COLUMN series TEXT NOT NULL DEFAULT ''"),
            ("series_order", "ALTER TABLE posts ADD COLUMN series_order INTEGER"),
            ("post_type", "ALTER TABLE posts ADD COLUMN post_type TEXT NOT NULL DEFAULT 'post'"),
            ("assets_meta", "ALTER TABLE posts ADD COLUMN assets_meta TEXT NOT NULL DEFAULT '{}'"),
        ]
        for col, ddl in migrations:
            if col not in existing_cols:
                await self._db.execute(ddl)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(date DESC)
        """)

        await self._db.commit()

    async def upsert_post(self, post, assets_meta: Optional[dict] = None) -> None:
        """Insert or update a post in the taxonomy."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        tags_json = json.dumps(post.tags)
        cover = getattr(post, "cover", None) or ""
        series = getattr(post, "series", None) or ""
        series_order = getattr(post, "series_order", None)
        post_type = getattr(post, "post_type", None) or "post"
        assets_json = json.dumps(assets_meta) if assets_meta is not None else None

        if assets_json is None:
            existing = await self.get_post(post.slug)
            assets_json = json.dumps(existing.get("assets_meta", {})) if existing else "{}"

        await self._db.execute("""
            INSERT INTO posts (
                slug, title, date, tags, reading_time, excerpt,
                cover, series, series_order, post_type, assets_meta, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                title = excluded.title,
                date = excluded.date,
                tags = excluded.tags,
                reading_time = excluded.reading_time,
                excerpt = excluded.excerpt,
                cover = excluded.cover,
                series = excluded.series,
                series_order = excluded.series_order,
                post_type = excluded.post_type,
                assets_meta = excluded.assets_meta,
                updated_at = excluded.updated_at
        """, (
            post.slug,
            post.title,
            post.date,
            tags_json,
            post.reading_time,
            post.excerpt,
            cover,
            series,
            series_order,
            post_type,
            assets_json,
            now,
            now,
        ))

        await self._db.commit()

    async def delete_post(self, slug: str) -> None:
        """Remove a post from the taxonomy."""
        await self._db.execute("DELETE FROM posts WHERE slug = ?", (slug,))
        await self._db.commit()

    async def get_post(self, slug: str) -> Optional[dict]:
        """Get a single post's metadata."""
        cursor = await self._db.execute(
            "SELECT * FROM posts WHERE slug = ?", (slug,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    async def list_posts(self, include_pages: bool = False) -> list[dict]:
        """List posts, newest first with deterministic tie-breaking by slug."""
        if include_pages:
            sql = "SELECT * FROM posts ORDER BY date DESC, slug ASC"
        else:
            sql = (
                "SELECT * FROM posts "
                "WHERE post_type = 'post' OR post_type IS NULL OR post_type = '' "
                "ORDER BY date DESC, slug ASC"
            )
        cursor = await self._db.execute(sql)
        rows = await cursor.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def list_pages(self) -> list[dict]:
        """List static pages ordered by slug."""
        cursor = await self._db.execute(
            "SELECT * FROM posts WHERE post_type = 'page' ORDER BY slug ASC"
        )
        rows = await cursor.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def list_by_tag(self, tag: str) -> list[dict]:
        """List posts with a specific tag, newest first."""
        posts = await self.list_posts(include_pages=False)
        target = tag.lower()
        return [p for p in posts if target in p["tags"]]

    async def list_all_tags(self) -> dict[str, int]:
        """Return mapping of tag -> post count across all blog posts."""
        posts = await self.list_posts(include_pages=False)
        counts: dict[str, int] = {}
        for p in posts:
            for t in p.get("tags", []):
                counts[t] = counts.get(t, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    async def close(self):
        """Close the database connection."""
        if self._db:
            await self._db.close()

    @staticmethod
    def _row_to_dict(row) -> dict:
        """Convert a database row to a dictionary with parsed tags and assets_meta."""
        d = dict(row)
        d["tags"] = json.loads(d["tags"])
        raw_assets = d.get("assets_meta")
        if isinstance(raw_assets, str):
            d["assets_meta"] = json.loads(raw_assets or "{}")
        elif raw_assets is None:
            d["assets_meta"] = {}
        return d
