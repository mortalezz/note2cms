"""
Taxonomy pipeline — PostgreSQL backend for cloud deployments.

Uses psycopg (v3) async interface, which works natively with
PgBouncer/connection poolers — no prepared statement issues.
"""

import asyncio
import json
import os
from typing import Optional

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool
    HAS_PSYCOPG = True
except ImportError:
    HAS_PSYCOPG = False


class PostgresTaxonomyDB:
    """PostgreSQL-backed taxonomy store. Same interface as TaxonomyDB."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._pool = None

    async def initialize(self):
        """Create the connection pool and table if needed."""
        self._pool = AsyncConnectionPool(
            self.database_url,
            min_size=1,
            max_size=5,
            open=False,
        )
        await self._pool.open()

        async with self._pool.connection() as conn:
            await conn.set_autocommit(True)
            async with conn.cursor() as cur:
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS posts (
                        slug TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        date TEXT NOT NULL,
                        tags JSONB NOT NULL DEFAULT '[]',
                        reading_time INTEGER NOT NULL DEFAULT 1,
                        excerpt TEXT NOT NULL DEFAULT '',
                        cover TEXT NOT NULL DEFAULT '',
                        series TEXT NOT NULL DEFAULT '',
                        series_order INTEGER,
                        post_type TEXT NOT NULL DEFAULT 'post',
                        pinned BOOLEAN NOT NULL DEFAULT FALSE,
                        assets_meta JSONB NOT NULL DEFAULT '{}',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                migrations = [
                    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS cover TEXT NOT NULL DEFAULT ''",
                    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS series TEXT NOT NULL DEFAULT ''",
                    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS series_order INTEGER",
                    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS post_type TEXT NOT NULL DEFAULT 'post'",
                    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE",
                    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS assets_meta JSONB NOT NULL DEFAULT '{}'",
                ]
                for ddl in migrations:
                    await cur.execute(ddl)
                await cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(date DESC)
                """)

    async def _retrying(self, fn, *, op_name: str):
        """
        Run a DB op and retry on transient OperationalError
        (e.g. unexpected EOF from managed Postgres / pooler).
        """
        delays = [0.2, 0.8]  # seconds, total 2 retries
        last_exc = None

        for attempt in range(len(delays) + 1):
            try:
                return await fn()
            except psycopg.OperationalError as e:
                last_exc = e
                if attempt >= len(delays):
                    break
                print(f"[db] OperationalError in {op_name}, retrying in {delays[attempt]}s")
                # Mark pool as unhealthy and reopen before retry.
                try:
                    if self._pool:
                        await self._pool.close()
                finally:
                    self._pool = AsyncConnectionPool(
                        self.database_url,
                        min_size=1,
                        max_size=5,
                        open=False,
                    )
                    await self._pool.open()
                await asyncio.sleep(delays[attempt])

        raise last_exc

    async def upsert_post(self, post, assets_meta: Optional[dict] = None) -> None:
        """Insert or update a post in the taxonomy."""
        tags_json = json.dumps(post.tags)
        cover = getattr(post, "cover", None) or ""
        series = getattr(post, "series", None) or ""
        series_order = getattr(post, "series_order", None)
        post_type = getattr(post, "post_type", None) or "post"
        pinned = bool(getattr(post, "pinned", False)) and post_type != "page"

        if assets_meta is None:
            existing = await self.get_post(post.slug)
            assets_json = json.dumps(existing.get("assets_meta", {})) if existing else "{}"
        else:
            assets_json = json.dumps(assets_meta)

        async def _op():
            async with self._pool.connection() as conn:
                await conn.set_autocommit(True)
                async with conn.cursor() as cur:
                    await cur.execute("""
                        INSERT INTO posts (
                            slug, title, date, tags, reading_time, excerpt,
                            cover, series, series_order, post_type, pinned, assets_meta, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW(), NOW())
                        ON CONFLICT (slug) DO UPDATE SET
                            title = EXCLUDED.title,
                            date = EXCLUDED.date,
                            tags = EXCLUDED.tags,
                            reading_time = EXCLUDED.reading_time,
                            excerpt = EXCLUDED.excerpt,
                            cover = EXCLUDED.cover,
                            series = EXCLUDED.series,
                            series_order = EXCLUDED.series_order,
                            post_type = EXCLUDED.post_type,
                            pinned = EXCLUDED.pinned,
                            assets_meta = EXCLUDED.assets_meta,
                            updated_at = NOW()
                    """, (
                        post.slug, post.title, post.date, tags_json,
                        post.reading_time, post.excerpt,
                        cover, series, series_order, post_type, pinned, assets_json,
                    ))

        await self._retrying(_op, op_name="upsert_post")

    async def delete_post(self, slug: str) -> None:
        """Remove a post from the taxonomy."""
        async def _op():
            async with self._pool.connection() as conn:
                await conn.set_autocommit(True)
                async with conn.cursor() as cur:
                    await cur.execute("DELETE FROM posts WHERE slug = %s", (slug,))

        await self._retrying(_op, op_name="delete_post")

    async def get_post(self, slug: str) -> Optional[dict]:
        """Get a single post's metadata."""
        async def _op():
            async with self._pool.connection() as conn:
                await conn.set_autocommit(True)
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute("SELECT * FROM posts WHERE slug = %s", (slug,))
                    row = await cur.fetchone()
                    if row is None:
                        return None
                    return self._row_to_dict(row)

        return await self._retrying(_op, op_name="get_post")

    async def list_posts(self, include_pages: bool = False) -> list[dict]:
        """List posts, newest first with deterministic tie-breaking by slug."""
        async def _op():
            async with self._pool.connection() as conn:
                await conn.set_autocommit(True)
                async with conn.cursor(row_factory=dict_row) as cur:
                    if include_pages:
                        await cur.execute("SELECT * FROM posts ORDER BY date DESC, slug ASC")
                    else:
                        await cur.execute(
                            "SELECT * FROM posts "
                            "WHERE post_type = 'post' OR post_type IS NULL OR post_type = '' "
                            "ORDER BY date DESC, slug ASC"
                        )
                    rows = await cur.fetchall()
                    return [self._row_to_dict(row) for row in rows]

        return await self._retrying(_op, op_name="list_posts")

    async def list_pages(self) -> list[dict]:
        """List static pages ordered by slug."""
        async def _op():
            async with self._pool.connection() as conn:
                await conn.set_autocommit(True)
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "SELECT * FROM posts WHERE post_type = 'page' ORDER BY slug ASC"
                    )
                    rows = await cur.fetchall()
                    return [self._row_to_dict(row) for row in rows]

        return await self._retrying(_op, op_name="list_pages")

    async def list_by_tag(self, tag: str) -> list[dict]:
        """List posts with a specific tag."""
        async def _op():
            async with self._pool.connection() as conn:
                await conn.set_autocommit(True)
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "SELECT * FROM posts "
                        "WHERE (post_type = 'post' OR post_type IS NULL OR post_type = '') "
                        "AND tags ? %s ORDER BY date DESC, slug ASC",
                        (tag.lower(),)
                    )
                    rows = await cur.fetchall()
                    return [self._row_to_dict(row) for row in rows]

        return await self._retrying(_op, op_name="list_by_tag")

    async def list_all_tags(self) -> dict[str, int]:
        """Return mapping of tag -> post count across all blog posts."""
        posts = await self.list_posts(include_pages=False)
        counts: dict[str, int] = {}
        for p in posts:
            for t in p.get("tags", []):
                counts[t] = counts.get(t, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    async def close(self):
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()

    @staticmethod
    def _row_to_dict(row) -> dict:
        """Convert a database row to a dictionary."""
        d = dict(row)
        d["pinned"] = bool(d.get("pinned", False))
        # psycopg returns JSONB as native Python types
        if isinstance(d.get("tags"), str):
            d["tags"] = json.loads(d["tags"])
        if isinstance(d.get("assets_meta"), str):
            d["assets_meta"] = json.loads(d["assets_meta"] or "{}")
        elif d.get("assets_meta") is None:
            d["assets_meta"] = {}
        # Convert timestamps to ISO strings
        for key in ("created_at", "updated_at"):
            if key in d and hasattr(d[key], "isoformat"):
                d[key] = d[key].isoformat()
        return d


def get_taxonomy_db():
    """
    Factory: returns PostgresTaxonomyDB if DATABASE_URL is set,
    otherwise falls back to SQLite TaxonomyDB.
    """
    database_url = os.getenv("DATABASE_URL")

    if database_url and database_url.startswith("postgresql"):
        if not HAS_PSYCOPG:
            raise ImportError(
                "psycopg[binary] and psycopg_pool are required for PostgreSQL. "
                "Add them to requirements.txt."
            )
        print(f"[taxonomy] Using PostgreSQL")
        return PostgresTaxonomyDB(database_url)
    else:
        from pipeline.taxonomy import TaxonomyDB
        db_path = os.getenv("DB_PATH", "./taxonomy.db")
        print(f"[taxonomy] Using SQLite: {db_path}")
        return TaxonomyDB(db_path)
