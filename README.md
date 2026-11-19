# note2cms

**Past-Browser Publishing Protocol (PBPP)**

*Write where you think. Publish where they look. Own everything in between.*

**[Live Demo →](https://garrul4ik.github.io/blog/)** · **[Manifesto](MANIFESTO.md)** · **[Deploy Guide (EN)](DEPLOY.md)** · **[Руководство по установке (RU)](INSTALL.md)**

---

## What Is This

A CMS that is not a CMS. A minimal FastAPI service that turns your notes app into a static blogging engine.

You write in Apple Notes, Bear, Obsidian, vim — wherever you think. You push Markdown (and optional images) to an endpoint. Two parallel pipelines fire: one builds static HTML + optimized WebP media + feeds in a single atomic commit, the other updates a lightweight taxonomy. You get a permalink back. Share it with the world.

No admin panel. No browser-based editor. No login screen. No monthly fee. No vendor lock-in. The output is static HTML served from a CDN. The infrastructure is disposable. Your words are the only thing that persists.

## How It Works

```
[Your Notes App / Obsidian / n2c CLI]
       │
       ▼  POST /publish (Bearer token)
  ┌──────────────────────────┐
  │  FastAPI (minimal API)   │
  │  ┌───────────┬─────────┐ │
  │  │ Pipeline 1│Pipeline 2│ │
  │  │  Jinja2   │ Taxonomy │ │
  │  │  + Media  │ + Source │ │
  │  └───────────┴─────────┘ │
  └──────────────────────────┘
       │              │
       ▼              ▼
  Static HTML    PostgreSQL/SQLite
  (GitHub Pages,   (post index &
   1 commit/pub)    raw markdown)
       │
       ▼
  Reader gets pure HTML + CSS
  Zero JavaScript. Instant load.
```

## The API

| Method   | Endpoint               | Description                                |
|----------|------------------------|--------------------------------------------|
| `POST`   | `/publish`             | Push Markdown (+ optional base64 `assets`) |
| `POST`   | `/media`               | Upload & process a single image asset      |
| `GET`    | `/posts/{slug}/source` | Get original Markdown back                 |
| `DELETE` | `/posts/{slug}`        | Remove a post and its assets               |
| `GET`    | `/posts`               | List posts (supports `tag`, `limit`, `offset`) |
| `GET`    | `/tags`                | List all tags with post counts             |
| `GET`    | `/search?q=...`        | Search posts by title, tags, and body      |
| `POST`   | `/rebuild`             | Re-render the entire site in one commit    |
| `POST`   | `/import-from-blog`    | Recover posts from GitHub Pages into DB    |

Static outputs generated on publish:
- **Stable O(1) Pagination**: `/posts/` (newest) and permanent `/posts/page/{n}/` archive pages (`PAGINATION_MODE=stable`, `POSTS_PER_PAGE=10`).
- **Zero-JS Image Carousel**: Consecutive images in a paragraph, `![[obsidian.jpg]]` embeds, or `::: gallery ... :::` blocks become CSS scroll-snap carousels with `:target` lightbox. Uploaded images have EXIF/GPS stripped and are resized to `<= 1 MP` with responsive WebP `srcset`.
- **Tag Archives**: `/posts/tags/` and paginated `/posts/tags/{tag}/`.
- **Feeds & SEO**: `/feed.xml` (RSS 2.0), `/atom.xml` (Atom 1.0), `/sitemap.xml`, `/robots.txt`, and auto-generated 1200×630 theme-matched OG cards (`og.png`) for text-only posts.
- **Internal Navigation & Sharing**: Previous/Next posts, `series:` / `series_order:` series TOC, related posts, static pages (`type: page`), pinned posts (`pinned: true` shown across index, archive, and tag pages), and native OS share + copy-link buttons below every post.
- **Optional Static Search**: Set `SEARCH=true` to generate `/search-index.json` and `/posts/search/`.
- **Localization**: Set `SITE_LANG=ru` or `en` for localized dates and UI labels.

## Frontmatter & Carousel Syntax

```yaml
---
title: Elbrus Hike        # Required
tags: [travel, mountains] # Optional
date: 2026-03-16          # Optional (UTC ISO-8601 normalized; defaults to now)
slug: elbrus-hike         # Optional (auto-derived from title)
excerpt: Short summary    # Optional (auto-extracted from first paragraph)
cover: 01.jpg             # Optional (image URL or uploaded asset name)
series: Caucasus 2026     # Optional series name
series_order: 1           # Optional integer position in series
type: post                # Optional: "post" (default) or "page"
carousel: true            # Optional: false disables auto-carousel for this post
pinned: false             # Optional: true pins the post at the top across all index/archive/tag pages
---
```

Consecutive images in a paragraph (or Obsidian `![[photo.jpg]]` embeds) automatically become a zero-JS scroll-snap carousel, or you can configure options explicitly:

```markdown
::: gallery caption="Sunrise at 4,800m" ratio=4/3
![Base camp](01.jpg)
![Summit](02.jpg)
:::
```

## Theme Usage

note2cms ships with **21 Jinja2 themes** in `themes/<theme_name>/`, sharing common zero-JS partials from `themes/_shared/`:

- `themes/<theme_name>/index.html` — template for index, paginated archives, tags, and search
- `themes/<theme_name>/post.html` — template for a single post or static page

### How to choose or switch a theme

The active theme is controlled by the `ACTIVE_THEME` environment variable (in FastAPI Cloud or `.env` for self-hosting):

```
ACTIVE_THEME=swiss
```

After changing it:

1. Restart/rebuild the service.
2. Rebuild posts to apply the new theme across the full archive:

```bash
curl -X POST https://YOUR_API_URL/rebuild \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### How to create or customize a theme

The easiest approach is to copy an existing theme (for example, `themes/default/` or `themes/swiss/`) into a new directory and modify `index.html` and `post.html` for your style. The core rendering logic stays the same: the pipeline injects post data, while the theme controls the HTML/CSS presentation.

For template variables, structure, and examples, see **[THEMING.md](THEMING.md)**.

## Deployment

note2cms runs for free. The entire stack:

| Component       | Free Tier                          |
|-----------------|------------------------------------|
| **API Runtime** | [FastAPI Cloud](https://fastapicloud.com) |
| **Database**    | [Neon](https://neon.tech) PostgreSQL |
| **Static Host** | GitHub Pages / Cloudflare Pages    |
| **SSL**         | Automatic via GitHub Pages         |
| **CDN**         | Automatic via GitHub Pages         |

**Total cost: a domain name. Twelve dollars a year.**

See **[DEPLOY.md](DEPLOY.md)** (EN) or **[INSTALL.md](INSTALL.md)** (RU) for the complete step-by-step installation guide.

## Publishing

From the command line:

```bash
curl -X POST https://your-api.fastapicloud.dev/publish \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"markdown": "---\ntitle: Hello World\ntags: [first]\n---\n\nMy first post."}'
```

From a Markdown file:

```bash
jq -Rs '{markdown: .}' post.md | curl -X POST \
  https://your-api.fastapicloud.dev/publish \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d @-
```

From iOS: a Shortcut that reads your note, wraps it in JSON, POSTs to the endpoint, copies the permalink.

From Android: a Share Intent to any HTTP client app.

## Editing

Want to edit a post? Get your original Markdown back:

```bash
curl https://your-api.fastapicloud.dev/posts/hello-world/source \
  -H "Authorization: Bearer YOUR_TOKEN" > post.md
```

Edit it in your notes app. Push it again. Same slug, updated content, rebuilt HTML.

## Architecture Principles

- **O(1) builds.** Publish one post, update only the post, its immediate neighbors, and the current page (`stable` pagination) — committed in a single Git Data API operation.
- **Markdown is the system of record.** Database and HTML are derived. Delete them, rebuild from source.
- **Build pipeline is disposable.** Workers wake up, transform via Jinja2, vanish. No residual state.
- **A theme is a function.** Data in, markup out via Jinja2 templates and shared partials.
- **Infrastructure is replaceable.** Move to any server, any host, any database. Only the domain matters.

## Self-Hosting

For those who prefer their own server over free tiers:

```bash
git clone https://github.com/mortalezz/note2cms.git
cd note2cms
pip install -r requirements.txt
python -c "import secrets; print(secrets.token_urlsafe(32))"  # your API token

# Set environment variables
export API_TOKEN=your-generated-token
export SITE_TITLE="My Blog"
export SITE_URL=http://localhost:8000

uvicorn api.main:app --host 0.0.0.0 --port 8000
```

SQLite taxonomy, local filesystem, no external dependencies. rsync it, git it, tar it. The infrastructure is replaceable. Your words are not.

## Publishing Clients

- **CLI (`n2c`)**: Installed as `n2c` via `pip install -e .` (`cli/n2c.py`).
  - `n2c config --url https://your-api --token YOUR_TOKEN`
  - `n2c publish note.md --write-back` (automatically discovers and uploads referenced local images & `![[embeds]]`)
  - `n2c sync ./vault/blog` (publishes only modified `.md` files and assets)
  - `n2c pull <slug>`, `n2c list`, `n2c delete <slug>`, `n2c rebuild`
- **Obsidian Plugin**: [garrul4ik/note2cms-publisher](https://github.com/garrul4ik/note2cms-publisher) — dedicated Obsidian plugin repository (publish, image/carousel bundling, preflight, offline queue, rebuild).

## Configuration

See [.env.example](.env.example) for all options:

| Variable | Default | Description |
|---|---|---|
| `API_TOKEN` | — | Bearer token for write endpoints |
| `SITE_TITLE` | `My Blog` | Blog title |
| `SITE_URL` | `http://localhost:8000` | Public base URL (no trailing slash) |
| `SITE_LANG` | `en` | UI & date formatting language (`en` or `ru`) |
| `ACTIVE_THEME` | `default` | Active Jinja2 theme name from `themes/` |
| `POSTS_PER_PAGE` | `10` | Posts per index/tag page |
| `PAGINATION_MODE` | `stable` | `stable` (O(1) permanent archives) or `classic` |
| `GALLERY_AUTO` | `true` | Auto-convert consecutive images into zero-JS carousels |
| `MAX_IMAGE_MP` | `1.0` | Maximum uploaded image resolution in megapixels |
| `MAX_ASSET_MB` | `15.0` | Maximum uploaded image payload size in MB |
| `FEED_FULL_TEXT` | `true` | Include full HTML post bodies in RSS/Atom feeds |
| `SEARCH` | `false` | Build static `/search-index.json` and `/posts/search/` |
| `NAV_PAGES` | — | Comma-separated `type: page` slugs to list in navigation |
| `CORS_ORIGINS` | `*` | Comma-separated allowed CORS origins |

## What's New

### v0.3.1 (2026-11-18)
- **Post Share Bar**: Native OS share (`navigator.share`) and copy-link buttons with localized feedback at the bottom of every post across all 21 themes.
- **Pinned Posts (`pinned: true`)**: Decoupled pinned post slot displaying a full featured card on the main index and a compact banner across all archive (`/posts/page/{n}/`) and tag (`/posts/tags/{tag}/`) pages without shifting `stable` pagination slices.

### v0.3.0 (2026-11-18)
- **Stable O(1) Pagination (`PAGINATION_MODE=stable`)**: Archive pages are sliced oldest-first so existing `/posts/page/{n}/` URLs never shift when new posts are published (with `classic` mode also supported), plus `tag`/`limit`/`offset` and `X-Total-Count` on `GET /posts`.
- **1 MP Media Pipeline & Strictly Zero-JS Carousel**: Added `assets` upload in `POST /publish` and `POST /media` with automatic EXIF/GPS stripping, EXIF auto-orientation, proportional downscaling to `<= 1 MP`, and responsive WebP `srcset`. Consecutive images, Obsidian `![[...]]` embeds, and `::: gallery ... :::` blocks render into pure-CSS `scroll-snap` carousels with `:target` lightbox and zero JavaScript.
- **Tag Archives**: Added `/posts/tags/` overview, paginated `/posts/tags/{tag}/` archives, clickable tags in all 21 themes, and `GET /tags`.
- **RSS / Atom / Sitemap / OG Cards**: Added `/feed.xml`, `/atom.xml`, `/sitemap.xml`, `/robots.txt`, and automatic 1200×630 theme-styled PNG social cards (`og.png`) for text-only posts.
- **Internal Blog Navigation**: Added Prev/Next post links, `series:` / `series_order:` TOC boxes, related posts by shared tags, and static pages (`type: page` + `NAV_PAGES`).
- **Search & Localization**: Added `GET /search?q=...`, optional static search (`/posts/search/` + `/search-index.json` via `SEARCH=true`), and `SITE_LANG=en|ru` with cross-platform date formatting.
- **Unified Jinja2 Renderer & Single-Commit Deploys**: Retired the Vite/React renderer, introduced `themes/_shared/` partials, `autoescape=True`, `SourceStore` abstraction, and atomic single-commit GitHub Git Data API deploys (`DeployBatch`).
- **Publishing Clients & Tests**: Added the official `n2c` CLI (`cli/n2c.py`), updated the Obsidian plugin (`note2cms-publisher` v1.3.0) with image/carousel uploads and `Rebuild blog`, hardened auth/CORS/error codes, and added a 36-test `pytest` suite.

### v0.2.0 (2026-03-31 – 2026-11-03)
- **FastAPI Cloud + Neon PostgreSQL**: Migrated cloud hosting from Leapcell to FastAPI Cloud + Neon serverless PostgreSQL (`DEPLOY.md`, `INSTALL.md`, `pyproject.toml`).
- **Post Recovery**: Added `POST /import-from-blog`, `migrate_from_blog.py`, and `pipeline/migrator.py` to reconstruct Markdown frontmatter and taxonomy directly from GitHub Pages.
- **Visual Flair Themes & Guides**: Added `ink`, `darkroom`, and `manuscript` themes, dark mode across light themes, plus `THEMING.md` and `CONTRIBUTING.md`.

### v0.1.0 (2026-03-16 – 2026-03-21)
- **Core PBPP Engine**: Released FastAPI publishing API (`/publish`, `/posts/{slug}/source`, `DELETE /posts/{slug}`, `/posts`, `/rebuild`), Markdown parser, SQLite & PostgreSQL (`psycopg3` + PgBouncer-safe + retry backoff) backends, and GitHub Pages deployer.
- **Theme Pack**: Shipped `default`, `swiss`, `brutalist`, `brutalist2`, `terminal`, `vaporwave`, and 12 Obsidian-inspired themes.

## Project Structure

```
note2cms/
├── api/
│   └── __init__.py          # FastAPI endpoints & incremental publish orchestrator
├── cli/
│   └── n2c.py               # Official CLI client (n2c)
├── pipeline/
│   ├── parser.py            # Markdown + frontmatter → structured post
│   ├── media.py             # EXIF/GPS strip, 1 MP cap, WebP srcset
│   ├── markdown_ext.py      # Obsidian embeds & zero-JS CSS carousel
│   ├── paginator.py         # Stable (O(1)) and classic pagination
│   ├── og.py                # 1200x630 Pillow OG social card generator
│   ├── feeds.py             # RSS 2.0, Atom 1.0, sitemap.xml, robots.txt
│   ├── search.py            # Static search index + API ranking
│   ├── i18n.py              # Cross-platform date & UI localization (en/ru)
│   ├── source_store.py      # Abstract Markdown source storage (FS / Postgres)
│   ├── builder_cloud.py     # Unified Jinja2 renderer
│   ├── builder.py           # Local wrapper for rebuild.py
│   ├── migrator.py          # GitHub Pages HTML → Markdown recovery
│   ├── taxonomy.py          # SQLite backend
│   ├── taxonomy_pg.py       # PostgreSQL backend
│   └── deployer.py          # Single-commit GitHub Data API & LocalDeployer
├── themes/
│   ├── _shared/             # Shared zero-JS carousel, pagination, nav & extras
│   └── default/             # Plus 20 more Jinja2 themes
├── tests/                   # Pytest test suite
├── DEPLOY.md                # FastAPI Cloud + Neon guide (EN)
├── INSTALL.md               # FastAPI Cloud + Neon guide (RU)
├── THEMING.md               # Three-layer theming guide
├── CONTRIBUTING.md          # Protocol & contribution guidelines
├── MANIFESTO.md             # Why this exists
└── README.md                # You are here
```

## License

MIT — because your publishing tool shouldn't have strings attached either.

---

*You are not gifting your writings to some dirty SaaS. You own it.*
