"""
Taxonomy pipeline — PostgreSQL backend for cloud deployments.

Uses psycopg (v3) async interface, which works natively with
PgBouncer/connection poolers — no prepared statement issues.
"""

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
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                await cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(date DESC)
                """)

    async def upsert_post(self, post) -> None:
        """Insert or update a post in the taxonomy."""
        tags_json = json.dumps(post.tags)

        async with self._pool.connection() as conn:
            await conn.set_autocommit(True)
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO posts (slug, title, date, tags, reading_time, excerpt, created_at, updated_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, NOW(), NOW())
                    ON CONFLICT (slug) DO UPDATE SET
                        title = EXCLUDED.title,
                        date = EXCLUDED.date,
                        tags = EXCLUDED.tags,
                        reading_time = EXCLUDED.reading_time,
                        excerpt = EXCLUDED.excerpt,
                        updated_at = NOW()
                """, (post.slug, post.title, post.date, tags_json,
                      post.reading_time, post.excerpt))

    async def delete_post(self, slug: str) -> None:
        """Remove a post from the taxonomy."""
        async with self._pool.connection() as conn:
            await conn.set_autocommit(True)
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM posts WHERE slug = %s", (slug,))

    async def get_post(self, slug: str) -> Optional[dict]:
        """Get a single post's metadata."""
        async with self._pool.connection() as conn:
            await conn.set_autocommit(True)
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM posts WHERE slug = %s", (slug,))
                row = await cur.fetchone()
                if row is None:
                    return None
                return self._row_to_dict(row)

    async def list_posts(self) -> list[dict]:
        """List all posts, newest first."""
        async with self._pool.connection() as conn:
            await conn.set_autocommit(True)
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM posts ORDER BY date DESC")
                rows = await cur.fetchall()
                return [self._row_to_dict(row) for row in rows]

    async def list_by_tag(self, tag: str) -> list[dict]:
        """List posts with a specific tag."""
        async with self._pool.connection() as conn:
            await conn.set_autocommit(True)
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM posts WHERE tags ? %s ORDER BY date DESC",
                    (tag.lower(),)
                )
                rows = await cur.fetchall()
                return [self._row_to_dict(row) for row in rows]

    async def close(self):
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()

    @staticmethod
    def _row_to_dict(row) -> dict:
        """Convert a database row to a dictionary."""
        d = dict(row)
        # psycopg returns JSONB as native Python types
        if isinstance(d.get("tags"), str):
            d["tags"] = json.loads(d["tags"])
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
