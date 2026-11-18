# note2cms

**Past-Browser Publishing Protocol (PBPP)**

*Write where you think. Publish where they look. Own everything in between.*

**[Live Demo →](https://mortalezz.github.io/blog/)** · **[Manifesto](MANIFESTO.md)** · **[Deploy for Free](INSTALL.md)**

---

## What Is This

A CMS that is not a CMS. Four API endpoints that turn your notes app into a blogging tool.

You write in Apple Notes, Bear, Obsidian, vim — wherever you think. You push Markdown to an endpoint. Two parallel pipelines fire: one builds a beautiful static HTML page, the other updates a lightweight taxonomy. You get a permalink back. Share it with the world.

No admin panel. No browser-based editor. No login screen. No monthly fee. No vendor lock-in. The output is static HTML served from a CDN. The infrastructure is disposable. Your words are the only thing that persists.

## How It Works

```
[Your Notes App]
       │
       ▼  POST /publish (Bearer token)
  ┌────────────────────────┐
  │  FastAPI (4 endpoints)  │
  │  ┌──────────┬─────────┐ │
  │  │ Pipeline 1│Pipeline 2│ │
  │  │  Build    │ Taxonomy │ │
  │  │  HTML     │ Index    │ │
  │  └──────────┴─────────┘ │
  └────────────────────────┘
       │              │
       ▼              ▼
  Static HTML    PostgreSQL/SQLite
  (GitHub Pages,    (post index)
   Cloudflare,
   any CDN)
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

Static outputs generated on publish:
- **Stable O(1) Pagination**: `/posts/` (newest) and permanent `/posts/page/{n}/` archive pages (`PAGINATION_MODE=stable`, `POSTS_PER_PAGE=10`).
- **Zero-JS Image Carousel**: Consecutive images in a paragraph, `![[obsidian.jpg]]` embeds, or `::: gallery ... :::` blocks become CSS scroll-snap carousels with `:target` lightbox. Uploaded images have EXIF/GPS stripped and are resized to `<= 1 MP` with responsive WebP `srcset`.
- **Tag Archives**: `/posts/tags/` and paginated `/posts/tags/{tag}/`.
- **Feeds & SEO**: `/feed.xml` (RSS 2.0), `/atom.xml` (Atom 1.0), `/sitemap.xml`, `/robots.txt`, and auto-generated 1200×630 theme-matched OG cards (`og.png`) for text-only posts.
- **Internal Navigation**: Previous/Next posts, `series:` / `series_order:` series TOC, related posts, and static pages (`type: page`).
- **Optional Static Search**: Set `SEARCH=true` to generate `/search-index.json` and `/posts/search/`.
- **Localization**: Set `SITE_LANG=ru` or `en` for localized dates and UI labels.

## Theme Usage

A theme consists of two templates in `themes/<theme_name>/`:

- `themes/<theme_name>/index.html` — template for the posts list page
- `themes/<theme_name>/post.html` — template for a single post page

### How to choose or switch a theme

The active theme is controlled by the `ACTIVE_THEME` environment variable (for example, in Leapcell or in `.env` for self-hosting):

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

See **[INSTALL.md](INSTALL.md)** for the complete step-by-step installation guide, or **[MIGRATION.md](MIGRATION.md)** if you are migrating from Leapcell.

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

- **O(1) builds.** Publish one post, build one post. Your archive of 500 posts is untouched.
- **Markdown is the system of record.** Database and HTML are derived. Delete them, rebuild from source.
- **Build pipeline is disposable.** Workers wake up, transform, vanish. No residual state.
- **A theme is a function.** Data in, markup out. React, Jinja2, Svelte — the pipeline does not care.
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
- **Obsidian Plugin**: Located in [clients/obsidian-note2cms/](clients/obsidian-note2cms/README.md) — ready-to-use `manifest.json` + pre-bundled `main.js`.

## Project Structure

```
note2cms/
├── api/
│   └── __init__.py          # FastAPI endpoints & incremental publish orchestrator
├── cli/
│   └── n2c.py               # Official CLI client (n2c)
├── clients/
│   └── obsidian-note2cms/   # Obsidian Community Plugin (publish, pull, delete, rebuild)
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
│   ├── taxonomy.py          # SQLite backend
│   ├── taxonomy_pg.py       # PostgreSQL backend
│   └── deployer.py          # Single-commit GitHub Data API & LocalDeployer
├── themes/
│   ├── _shared/             # Shared zero-JS carousel, pagination, nav & extras
│   └── default/             # Plus 20 more Jinja2 themes
├── tests/                   # Pytest test suite
├── MANIFESTO.md
├── INSTALL.md
└── README.md
```

## License

MIT — because your publishing tool shouldn't have strings attached either.

---

*You are not gifting your writings to some dirty SaaS. You own it.*
