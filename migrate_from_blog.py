#!/usr/bin/env python3
"""
Local backup and migration script.

Usage:
    # Save local markdown backup without needing DATABASE_URL:
    python migrate_from_blog.py --save-markdown ./content

    # Or migrate directly to PostgreSQL if you have DATABASE_URL:
    python migrate_from_blog.py --database-url "postgresql://..."
"""

import os
import sys
import json
import argparse
from pathlib import Path

from pipeline.migrator import get_post_slugs, fetch_and_parse_post


def migrate_to_postgres(database_url: str, posts: list[dict]):
    """Insert posts into PostgreSQL posts and markdown_source tables."""
    try:
        import psycopg
    except ImportError:
        print("Error: 'psycopg' is required. Run: pip install psycopg[binary]")
        sys.exit(1)

    print(f"\n[db] Connecting to PostgreSQL...")
    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
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
            cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(date DESC)")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS markdown_source (
                    slug TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            for post in posts:
                cur.execute("""
                    INSERT INTO posts (slug, title, date, tags, reading_time, excerpt, created_at, updated_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, NOW(), NOW())
                    ON CONFLICT (slug) DO UPDATE SET
                        title = EXCLUDED.title,
                        date = EXCLUDED.date,
                        tags = EXCLUDED.tags,
                        reading_time = EXCLUDED.reading_time,
                        excerpt = EXCLUDED.excerpt,
                        updated_at = NOW()
                """, (
                    post["slug"],
                    post["title"],
                    post["date"],
                    json.dumps(post["tags"]),
                    post["reading_time"],
                    post["excerpt"],
                ))

                cur.execute("""
                    INSERT INTO markdown_source (slug, content, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (slug) DO UPDATE SET
                        content = EXCLUDED.content,
                        updated_at = NOW()
                """, (post["slug"], post["markdown"]))

    print(f"[db] ✓ Successfully wrote {len(posts)} posts into PostgreSQL.")


def main():
    parser = argparse.ArgumentParser(description="Migrate published posts from GitHub Pages")
    parser.add_argument("--repo", default="garrul4ik/blog", help="GitHub repo with blog")
    parser.add_argument("--branch", default="gh-pages", help="Git branch")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"), help="PostgreSQL connection string (optional)")
    parser.add_argument("--github-token", default=os.getenv("GITHUB_TOKEN"), help="GitHub token (optional)")
    parser.add_argument("--save-markdown", default=None, help="Directory to save recovered .md files (optional)")

    args = parser.parse_args()

    print(f"[*] Discovering posts in {args.repo}@{args.branch}...")
    slugs = get_post_slugs(args.repo, args.branch, args.github_token)
    print(f"[*] Found {len(slugs)} posts to migrate.")

    if not slugs:
        print("[!] No posts found.")
        sys.exit(1)

    parsed_posts = []
    for i, slug in enumerate(slugs, 1):
        try:
            p = fetch_and_parse_post(args.repo, args.branch, slug, args.github_token)
            parsed_posts.append(p)
            print(f"  [{i}/{len(slugs)}] ✓ {slug} — {p['title']}")
        except Exception as e:
            print(f"  [{i}/{len(slugs)}] ✗ {slug} — {e}")

    if args.save_markdown:
        out_dir = Path(args.save_markdown)
        out_dir.mkdir(parents=True, exist_ok=True)
        for post in parsed_posts:
            md_path = out_dir / f"{post['slug']}.md"
            md_path.write_text(post["markdown"], encoding="utf-8")
        print(f"\n[files] ✓ Saved {len(parsed_posts)} markdown files to {out_dir}/")

    if args.database_url:
        migrate_to_postgres(args.database_url, parsed_posts)

    print("\n✓ Done.")


if __name__ == "__main__":
    main()
