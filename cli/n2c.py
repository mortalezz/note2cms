"""
n2c — Command-line client for note2cms.

Config priority: CLI flags (--url, --token) > environment variables
(N2C_API_URL, N2C_API_TOKEN) > ~/.config/note2cms/config.json
"""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

import frontmatter
import httpx

MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
OBSIDIAN_IMAGE_RE = re.compile(r"!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def default_config_path() -> Path:
    return Path.home() / ".config" / "note2cms" / "config.json"


def load_config(
    url_flag: Optional[str] = None,
    token_flag: Optional[str] = None,
    config_path: Optional[Path] = None,
) -> tuple[str, str]:
    cfg_file = config_path or default_config_path()
    saved: dict = {}
    if cfg_file.exists():
        try:
            saved = json.loads(cfg_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            saved = {}

    url = (
        url_flag
        or os.getenv("N2C_API_URL")
        or saved.get("url")
        or "http://localhost:8000"
    ).rstrip("/")
    token = (
        token_flag
        or os.getenv("N2C_API_TOKEN")
        or saved.get("token")
        or ""
    )
    return url, token


def save_config(url: str, token: str, config_path: Optional[Path] = None) -> Path:
    cfg_file = config_path or default_config_path()
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"url": url.rstrip("/"), "token": token}
    cfg_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return cfg_file


def _find_local_asset(ref: str, note_dir: Path) -> Optional[Path]:
    clean = unquote(ref.strip().lstrip("./"))
    if not clean or clean.startswith(("http://", "https://", "data:", "/posts/")):
        return None
    candidates = [
        note_dir / clean,
        note_dir / "attachments" / clean,
        note_dir / "assets" / clean,
        note_dir / "images" / clean,
        note_dir / Path(clean).name,
        note_dir / "attachments" / Path(clean).name,
        note_dir / "assets" / Path(clean).name,
    ]
    for cand in candidates:
        if cand.is_file() and cand.suffix.lower() in IMAGE_EXTS:
            return cand
    return None


def collect_local_assets(markdown_text: str, note_dir: Path) -> dict[str, str]:
    """Scan Markdown for local image references and return {ref: base64}."""
    refs: list[str] = []
    refs.extend(MD_IMAGE_RE.findall(markdown_text))
    refs.extend(OBSIDIAN_IMAGE_RE.findall(markdown_text))

    # Also check frontmatter cover if it points to a local file
    try:
        parsed = frontmatter.loads(markdown_text)
        cover = parsed.metadata.get("cover")
        if isinstance(cover, str) and cover.strip():
            refs.append(cover.strip())
    except Exception:
        pass

    assets: dict[str, str] = {}
    for ref in dict.fromkeys(refs):
        asset_path = _find_local_asset(ref, note_dir)
        if asset_path is not None:
            assets[ref] = base64.b64encode(asset_path.read_bytes()).decode("ascii")
    return assets


def write_back_frontmatter(md_path: Path, slug: str, permalink: str) -> None:
    raw = md_path.read_text(encoding="utf-8")
    post = frontmatter.loads(raw)
    post.metadata["slug"] = slug
    post.metadata["permalink"] = permalink
    md_path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def cmd_publish(args, url: str, token: str, client: Optional[httpx.Client] = None) -> int:
    md_path = Path(args.file)
    if not md_path.is_file():
        print(f"Error: file not found: {md_path}", file=sys.stderr)
        return 1

    raw = md_path.read_text(encoding="utf-8")
    assets = collect_local_assets(raw, md_path.parent)
    payload: dict = {"markdown": raw}
    if assets:
        payload["assets"] = assets

    own_client = client is None
    http = client or httpx.Client(timeout=60.0)
    try:
        resp = http.post(f"{url}/publish", json=payload, headers=_auth_headers(token))
        if resp.status_code >= 400:
            print(f"Error {resp.status_code}: {resp.text}", file=sys.stderr)
            return 1
        data = resp.json()
    finally:
        if own_client:
            http.close()

    if args.write_back:
        write_back_frontmatter(md_path, data["slug"], data["permalink"])

    status_word = "Created" if data.get("created") else "Updated"
    print(f"{status_word}: {data['permalink']} (slug: {data['slug']})")
    if assets:
        print(f"Uploaded {len(assets)} asset(s): {', '.join(assets.keys())}")
    return 0


def cmd_pull(args, url: str, token: str, client: Optional[httpx.Client] = None) -> int:
    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        resp = http.get(
            f"{url}/posts/{args.slug}/source",
            headers=_auth_headers(token),
        )
        if resp.status_code >= 400:
            print(f"Error {resp.status_code}: {resp.text}", file=sys.stderr)
            return 1
        text = resp.text
    finally:
        if own_client:
            http.close()

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(text, encoding="utf-8")
        print(f"Saved source to {out_path}")
    else:
        print(text, end="" if text.endswith("\n") else "\n")
    return 0


def cmd_list(args, url: str, _token: str, client: Optional[httpx.Client] = None) -> int:
    params: dict = {}
    if args.tag:
        params["tag"] = args.tag
    if args.limit:
        params["limit"] = args.limit

    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        resp = http.get(f"{url}/posts", params=params)
        if resp.status_code >= 400:
            print(f"Error {resp.status_code}: {resp.text}", file=sys.stderr)
            return 1
        posts = resp.json()
    finally:
        if own_client:
            http.close()

    if not posts:
        print("No posts found.")
        return 0

    for p in posts:
        tags_str = ", ".join(p.get("tags", []))
        print(f"{p['slug']:30s} | {p['date'][:10]} | {p['title']} [{tags_str}]")
    return 0


def cmd_delete(args, url: str, token: str, client: Optional[httpx.Client] = None) -> int:
    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        resp = http.delete(f"{url}/posts/{args.slug}", headers=_auth_headers(token))
        if resp.status_code >= 400:
            print(f"Error {resp.status_code}: {resp.text}", file=sys.stderr)
            return 1
    finally:
        if own_client:
            http.close()

    print(f"Deleted: {args.slug}")
    return 0


def cmd_rebuild(_args, url: str, token: str, client: Optional[httpx.Client] = None) -> int:
    own_client = client is None
    http = client or httpx.Client(timeout=120.0)
    try:
        resp = http.post(f"{url}/rebuild", headers=_auth_headers(token))
        if resp.status_code >= 400:
            print(f"Error {resp.status_code}: {resp.text}", file=sys.stderr)
            return 1
        data = resp.json()
    finally:
        if own_client:
            http.close()

    print(f"Rebuilt {data.get('posts', 0)} post(s).")
    return 0


def cmd_sync(args, url: str, token: str, client: Optional[httpx.Client] = None) -> int:
    target_dir = Path(args.directory)
    if not target_dir.is_dir():
        print(f"Error: directory not found: {target_dir}", file=sys.stderr)
        return 1

    state_file = target_dir / ".n2c-sync.json"
    state: dict[str, str] = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}

    md_files = sorted(p for p in target_dir.glob("*.md"))
    published = 0
    skipped = 0

    own_client = client is None
    http = client or httpx.Client(timeout=60.0)
    try:
        for md_path in md_files:
            raw = md_path.read_text(encoding="utf-8")
            assets = collect_local_assets(raw, md_path.parent)
            # Hash markdown + attached assets so editing an image also triggers sync
            hasher = hashlib.sha256(raw.encode("utf-8"))
            for k in sorted(assets.keys()):
                hasher.update(k.encode("utf-8"))
                hasher.update(assets[k].encode("utf-8"))
            digest = hasher.hexdigest()

            if state.get(md_path.name) == digest and not args.force:
                skipped += 1
                continue

            payload: dict = {"markdown": raw}
            if assets:
                payload["assets"] = assets

            resp = http.post(f"{url}/publish", json=payload, headers=_auth_headers(token))
            if resp.status_code >= 400:
                print(f"Error syncing {md_path.name} ({resp.status_code}): {resp.text}", file=sys.stderr)
                return 1
            data = resp.json()
            state[md_path.name] = digest
            published += 1
            print(f"Synced: {md_path.name} -> {data['permalink']}")
    finally:
        if own_client:
            http.close()

    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"Sync complete: {published} published, {skipped} unchanged.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="n2c", description="note2cms publishing CLI")
    parser.add_argument("--url", help="note2cms API base URL")
    parser.add_argument("--token", help="note2cms Bearer token")

    sub = parser.add_subparsers(dest="command", required=True)

    p_cfg = sub.add_parser("config", help="Save API URL and token")
    p_cfg.add_argument("--url", dest="cfg_url", help="API URL to save")
    p_cfg.add_argument("--token", dest="cfg_token", help="API token to save")

    p_pub = sub.add_parser("publish", help="Publish a Markdown file (with local images)")
    p_pub.add_argument("file", help="Path to Markdown note")
    p_pub.add_argument("--write-back", action="store_true", help="Write slug & permalink into frontmatter")

    p_pull = sub.add_parser("pull", help="Fetch original Markdown source for a slug")
    p_pull.add_argument("slug", help="Post slug")
    p_pull.add_argument("-o", "--output", help="Write output to file")

    p_list = sub.add_parser("list", help="List published posts")
    p_list.add_argument("--tag", help="Filter by tag")
    p_list.add_argument("--limit", type=int, help="Maximum posts to display")

    p_del = sub.add_parser("delete", help="Delete a published post")
    p_del.add_argument("slug", help="Post slug")

    sub.add_parser("rebuild", help="Re-render all posts on the server")

    p_sync = sub.add_parser("sync", help="Publish changed Markdown files in a directory")
    p_sync.add_argument("directory", help="Directory containing .md files")
    p_sync.add_argument("--force", action="store_true", help="Republish all files regardless of hash")

    return parser


def main(argv: Optional[list[str]] = None, client: Optional[httpx.Client] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "config":
        current_url, current_token = load_config(args.url, args.token)
        new_url = args.cfg_url or current_url
        new_token = args.cfg_token or current_token
        if args.cfg_url or args.cfg_token:
            saved_path = save_config(new_url, new_token)
            print(f"Saved configuration to {saved_path}")
        else:
            masked = f"{current_token[:4]}..." if len(current_token) > 4 else "(unset)"
            print(f"URL: {current_url}\nToken: {masked}")
        return 0

    url, token = load_config(args.url, args.token)

    dispatch = {
        "publish": cmd_publish,
        "pull": cmd_pull,
        "list": cmd_list,
        "delete": cmd_delete,
        "rebuild": cmd_rebuild,
        "sync": cmd_sync,
    }
    return dispatch[args.command](args, url, token, client=client)


if __name__ == "__main__":
    raise SystemExit(main())
