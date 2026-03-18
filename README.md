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

| Method   | Endpoint               | Description                    |
|----------|------------------------|--------------------------------|
| `POST`   | `/publish`             | Push Markdown, get a permalink |
| `GET`    | `/posts/{slug}/source` | Get original Markdown back     |
| `DELETE` | `/posts/{slug}`        | Remove a post                  |
| `GET`    | `/posts`               | List all posts                 |

That's the whole CMS.

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
| **API Runtime** | [Leapcell](https://leapcell.io)    |
| **Database**    | Leapcell PostgreSQL                |
| **Static Host** | GitHub Pages / Cloudflare Pages    |
| **SSL**         | Automatic via GitHub Pages         |
| **CDN**         | Automatic via GitHub Pages         |

**Total cost: a domain name. Twelve dollars a year.**

See **[INSTALL.md](INSTALL.md)** for the complete step-by-step deployment guide.

## Publishing

From the command line:

```bash
curl -X POST https://your-api.leapcell.dev/publish \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"markdown": "---\ntitle: Hello World\ntags: [first]\n---\n\nMy first post."}'
```

From a Markdown file:

```bash
jq -Rs '{markdown: .}' post.md | curl -X POST \
  https://your-api.leapcell.dev/publish \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d @-
```

From iOS: a Shortcut that reads your note, wraps it in JSON, POSTs to the endpoint, copies the permalink.

From Android: a Share Intent to any HTTP client app.

## Editing

Want to edit a post? Get your original Markdown back:

```bash
curl https://your-api.leapcell.dev/posts/hello-world/source \
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

## Project Structure

```
note2cms/
├── api/
│   └── __init__.py          # The 4 endpoints. The whole CMS.
├── pipeline/
│   ├── parser.py            # Markdown + frontmatter → structured post
│   ├── builder_cloud.py     # Renders HTML in memory (cloud mode)
│   ├── builder.py           # Renders HTML to filesystem (local mode)
│   ├── taxonomy.py          # SQLite backend
│   ├── taxonomy_pg.py       # PostgreSQL backend (Leapcell/cloud)
│   └── deployer.py          # GitHub Pages deployer via API
├── themes/
│   └── default/
│       ├── post.html         # Jinja2 post template
│       ├── index.html        # Jinja2 index template
│       └── react/            # React SSR theme (optional)
│           ├── Post.jsx
│           ├── Index.jsx
│           └── theme.css
├── MANIFESTO.md              # Why this exists
├── INSTALL.md                # Free-tier deployment guide
└── README.md                 # You are here
```

## License

MIT — because your publishing tool shouldn't have strings attached either.

---

*You are not gifting your writings to some dirty SaaS. You own it.*
