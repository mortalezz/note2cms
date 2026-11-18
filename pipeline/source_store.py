"""
Source store — persists original Markdown documents (system of record).

Local mode uses the filesystem (`{content_dir}/{slug}.md`).
Cloud mode uses PostgreSQL (`markdown_source` table).
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class SourceStore(ABC):
    """Abstract interface for storing and retrieving raw Markdown sources."""

    @abstractmethod
    async def initialize(self) -> None:
        """Prepare underlying storage."""

    @abstractmethod
    async def put(self, slug: str, markdown: str) -> None:
        """Store or overwrite raw Markdown for a slug."""

    @abstractmethod
    async def get(self, slug: str) -> Optional[str]:
        """Retrieve raw Markdown for a slug, or None if missing."""

    @abstractmethod
    async def delete(self, slug: str) -> None:
        """Remove raw Markdown for a slug."""

    @abstractmethod
    async def list_slugs(self) -> list[str]:
        """Return sorted list of stored post slugs."""


class FsSourceStore(SourceStore):
    """Filesystem-backed Markdown source store."""

    def __init__(self, content_dir: Path):
        self.content_dir = Path(content_dir)

    async def initialize(self) -> None:
        self.content_dir.mkdir(parents=True, exist_ok=True)

    async def put(self, slug: str, markdown: str) -> None:
        self.content_dir.mkdir(parents=True, exist_ok=True)
        (self.content_dir / f"{slug}.md").write_text(markdown, encoding="utf-8")

    async def get(self, slug: str) -> Optional[str]:
        md_path = self.content_dir / f"{slug}.md"
        if md_path.exists():
            return md_path.read_text(encoding="utf-8")
        return None

    async def delete(self, slug: str) -> None:
        md_path = self.content_dir / f"{slug}.md"
        if md_path.exists():
            md_path.unlink()

    async def list_slugs(self) -> list[str]:
        if not self.content_dir.exists():
            return []
        return sorted(p.stem for p in self.content_dir.glob("*.md"))


class PgSourceStore(SourceStore):
    """PostgreSQL-backed Markdown source store using an existing TaxonomyDB pool."""

    def __init__(self, taxonomy_db):
        self.taxonomy_db = taxonomy_db

    async def initialize(self) -> None:
        async def _op():
            async with self.taxonomy_db._pool.connection() as conn:
                await conn.set_autocommit(True)
                async with conn.cursor() as cur:
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS markdown_source (
                            slug TEXT PRIMARY KEY,
                            content TEXT NOT NULL,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                    """)

        await self.taxonomy_db._retrying(_op, op_name="ensure_source_table")

    async def put(self, slug: str, markdown: str) -> None:
        async def _op():
            async with self.taxonomy_db._pool.connection() as conn:
                await conn.set_autocommit(True)
                async with conn.cursor() as cur:
                    await cur.execute("""
                        INSERT INTO markdown_source (slug, content, updated_at)
                        VALUES (%s, %s, NOW())
                        ON CONFLICT (slug) DO UPDATE SET
                            content = EXCLUDED.content,
                            updated_at = NOW()
                    """, (slug, markdown))

        await self.taxonomy_db._retrying(_op, op_name="put_source")

    async def get(self, slug: str) -> Optional[str]:
        async def _op():
            async with self.taxonomy_db._pool.connection() as conn:
                await conn.set_autocommit(True)
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT content FROM markdown_source WHERE slug = %s",
                        (slug,),
                    )
                    row = await cur.fetchone()
                    return row[0] if row else None

        return await self.taxonomy_db._retrying(_op, op_name="get_source")

    async def delete(self, slug: str) -> None:
        async def _op():
            async with self.taxonomy_db._pool.connection() as conn:
                await conn.set_autocommit(True)
                async with conn.cursor() as cur:
                    await cur.execute(
                        "DELETE FROM markdown_source WHERE slug = %s",
                        (slug,),
                    )

        await self.taxonomy_db._retrying(_op, op_name="delete_source")

    async def list_slugs(self) -> list[str]:
        async def _op():
            async with self.taxonomy_db._pool.connection() as conn:
                await conn.set_autocommit(True)
                async with conn.cursor() as cur:
                    await cur.execute("SELECT slug FROM markdown_source ORDER BY slug ASC")
                    rows = await cur.fetchall()
                    return [r[0] for r in rows]

        return await self.taxonomy_db._retrying(_op, op_name="list_source_slugs")


def get_source_store(db, content_dir: Path, cloud_mode: bool) -> SourceStore:
    """Return the appropriate SourceStore for local or cloud mode."""
    if cloud_mode and hasattr(db, "_pool"):
        return PgSourceStore(db)
    return FsSourceStore(content_dir)
