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
        """Create the database and table if they don't exist."""
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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(date DESC)
        """)

        await self._db.commit()

    async def upsert_post(self, post) -> None:
        """Insert or update a post in the taxonomy."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        tags_json = json.dumps(post.tags)

        await self._db.execute("""
            INSERT INTO posts (slug, title, date, tags, reading_time, excerpt, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                title = excluded.title,
                date = excluded.date,
                tags = excluded.tags,
                reading_time = excluded.reading_time,
                excerpt = excluded.excerpt,
                updated_at = excluded.updated_at
        """, (
            post.slug,
            post.title,
            post.date,
            tags_json,
            post.reading_time,
            post.excerpt,
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

    async def list_posts(self) -> list[dict]:
        """List all posts, newest first."""
        cursor = await self._db.execute(
            "SELECT * FROM posts ORDER BY date DESC"
        )
        rows = await cursor.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def list_by_tag(self, tag: str) -> list[dict]:
        """List posts with a specific tag."""
        cursor = await self._db.execute(
            "SELECT * FROM posts ORDER BY date DESC"
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            post = self._row_to_dict(row)
            if tag.lower() in post["tags"]:
                results.append(post)
        return results

    async def close(self):
        """Close the database connection."""
        if self._db:
            await self._db.close()

    @staticmethod
    def _row_to_dict(row) -> dict:
        """Convert a database row to a dictionary with parsed tags."""
        d = dict(row)
        d["tags"] = json.loads(d["tags"])
        return d
