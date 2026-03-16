#!/usr/bin/env python3
"""
Rebuild everything from source Markdown.

Your content directory is the system of record. This script
reconstructs the taxonomy database and all static HTML from scratch.
Use it after theme changes, migrations, or disaster recovery.

Usage:
    python rebuild.py
    python rebuild.py --content ./content --static ./static --theme default
"""

import asyncio
import argparse
from pathlib import Path

from pipeline.taxonomy import TaxonomyDB
from pipeline.builder import BuildPipeline
from pipeline.parser import parse_markdown


async def rebuild(
    content_dir: str = "./content",
    static_dir: str = "./static",
    themes_dir: str = "./themes",
    active_theme: str = "default",
    db_path: str = "./taxonomy.db",
    site_title: str = "My Blog",
    site_url: str = "http://localhost:8000",
):
    content = Path(content_dir)
    static = Path(static_dir)

    if not content.exists():
        print(f"Content directory {content} does not exist.")
        return

    md_files = sorted(content.glob("*.md"))
    print(f"Found {len(md_files)} Markdown files in {content}/")

    if not md_files:
        print("Nothing to rebuild.")
        return

    # Initialize subsystems
    db = TaxonomyDB(db_path)
    await db.initialize()

    builder = BuildPipeline(
        content_dir=content,
        static_dir=static,
        themes_dir=Path(themes_dir),
        active_theme=active_theme,
        site_title=site_title,
        site_url=site_url,
    )
    await builder.initialize()

    # Rebuild each post
    for md_file in md_files:
        raw = md_file.read_text(encoding="utf-8")
        try:
            post = parse_markdown(raw)
            await builder.build_post(post)
            await db.upsert_post(post)
            print(f"  ✓ {post.slug} — {post.title}")
        except Exception as e:
            print(f"  ✗ {md_file.name} — {e}")

    # Rebuild index
    posts = await db.list_posts()
    await builder.build_index(posts)
    print(f"\n✓ Rebuilt index with {len(posts)} posts")

    await db.close()
    print("✓ Done.")


def main():
    parser = argparse.ArgumentParser(description="Rebuild note2cms from source Markdown")
    parser.add_argument("--content", default="./content", help="Content directory")
    parser.add_argument("--static", default="./static", help="Static output directory")
    parser.add_argument("--themes", default="./themes", help="Themes directory")
    parser.add_argument("--theme", default="default", help="Active theme name")
    parser.add_argument("--db", default="./taxonomy.db", help="Database path")
    parser.add_argument("--site-title", default="My Blog", help="Site title")
    parser.add_argument("--site-url", default="http://localhost:8000", help="Site URL")

    args = parser.parse_args()
    asyncio.run(rebuild(
        content_dir=args.content,
        static_dir=args.static,
        themes_dir=args.themes,
        active_theme=args.theme,
        db_path=args.db,
        site_title=args.site_title,
        site_url=args.site_url,
    ))


if __name__ == "__main__":
    main()
