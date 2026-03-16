# note2cms

**Past-Browser Publishing Protocol (PBPP)**

*Write where you think. Publish where they look. Own everything in between.*

## Philosophy

Every CMS gets it backwards — they put the editor in the browser. But authoring
has already left. Apple Notes, Obsidian, Bear, vim, whatever you think in. note2cms
accepts Markdown from anywhere (Android Intent, iOS Shortcuts, curl) and produces
beautiful, static blog posts. No SaaS. No vendor lock-in. Your words, your server,
your domain.

## Architecture

```
[Your Notes App] → POST /publish → FastAPI
                                      ├── Pipeline 1: Build
                                      │   Parse MD → Inject into JSX → Vite build → Static HTML
                                      └── Pipeline 2: Taxonomy
                                          Extract metadata → SQLite → Rebuild index page
                                      → Returns permalink
```

## API (4 endpoints, that's the whole CMS)

| Method   | Endpoint              | Description                        |
|----------|-----------------------|------------------------------------|
| `POST`   | `/publish`            | Push Markdown, get a permalink     |
| `GET`    | `/posts/{slug}/source`| Get original Markdown back         |
| `DELETE` | `/posts/{slug}`       | Remove a post                      |
| `GET`    | `/posts`              | List all posts (taxonomy query)    |

## Theming

A theme is two JSX files:

- `Post.jsx` — receives `{title, date, content, tags, readingTime, slug}`
- `Index.jsx` — receives `{posts: [{title, date, tags, readingTime, slug, excerpt}]}`

Change your blog's entire look by swapping these two files. That's it.

## Setup

```bash
# Prerequisites: Python 3.11+, Node.js 18+
pip install fastapi uvicorn python-frontmatter python-slugify aiosqlite jinja2
npm install  # from project root

# Generate your auth token
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Put it in .env as API_TOKEN=<your-token>

# Run
uvicorn api.main:app --reload

# Publish your first post
curl -X POST http://localhost:8000/publish \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"markdown": "---\ntitle: Hello World\ntags: [first, test]\n---\n\nThis is my first post."}'
```

## Self-Hosting

This is a directory of Markdown files, a SQLite database, and static HTML.
rsync it. git it. tar it. Move to any server. Rebuild everything from source
Markdown in seconds. The infrastructure is replaceable. Your words are not.

## License

MIT — because your publishing tool shouldn't have strings attached either.
