# note2cms — SaaSless Publishing

*We cannot lose what we do not hold.*

---

note2cms is a publishing pipeline. Markdown in, static HTML out, permalink back. No account. No dashboard. No browser-based editor. No pricing page. Just a token and a pipeline.

This branch (`fastapicloud`) is the multi-tenant deployment on FastAPI Cloud. Anyone can register, get a token, and start publishing to their own GitHub Pages blog. The architecture is the same four endpoints, now aware of who's asking.

**Live demo:** https://note2cms.fastapicloud.dev

## How It Works

```
You → POST /register (GitHub repo + PAT)
    ← token

You → POST /publish (Bearer token + Markdown)
    ← permalink

Your readers → GitHub Pages (static HTML, zero compute)
```

One Neon table stores tokens and repo configs. No posts. No content. No Markdown. Your words live in your GitHub repo. The database is a doorman, not a warehouse.

## Register

```bash
curl -X POST https://note2cms.fastapicloud.dev/register \
  -H "Content-Type: application/json" \
  -d '{
    "github_repo": "username/blog",
    "github_token": "ghp_your_fine_grained_pat",
    "site_url": "https://username.github.io/blog"
  }'
```

Returns your publishing token. Save it. We do not store what we do not need.

Or use the registration form at the root URL — it previews your chosen theme in real-time before you register.

## Publish

```bash
curl -X POST https://note2cms.fastapicloud.dev/publish \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"markdown": "---\ntitle: Hello World\ntags: [first]\ndate: 2026-03-23\n---\n\nMy first post."}'
```

Returns a permalink. Your post is live on GitHub Pages. The pipeline ran, rendered your Markdown through your chosen theme, deployed static HTML to your repo, updated your index, and died. No residual process. No background worker. No daemon.

## Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | /register | No | Get a publishing token |
| POST | /publish | Yes | Push Markdown, get permalink |
| GET | /posts | Yes | List your posts |
| GET | /posts/{slug}/source | Yes | Get original Markdown back |
| DELETE | /posts/{slug} | Yes | Remove a post |
| POST | /rebuild | Yes | Re-render all posts (theme switch) |

## Themes

Eight themes ship with note2cms. Each has a distinct personality and a hidden visual trick.

| Theme | The Personality |
|---|---|
| `terminal` | Phosphor green on black, CRT scanlines, `##` headers |
| `brutalist` | IBM Plex Mono, 4px borders, binary hover inversion |
| `ink` | Japanese calligraphy, vermillion brushstroke on load |
| `darkroom` | Amber safelight, photographs that develop on scroll |
| `vaporwave` | Pink-purple gradients, floating card lift on hover |
| `manuscript` | Typed paper, red margin line, section annotations |
| `swiss` | Bauhaus geometry, primary color bar, numbered posts |
| `default` | Warm editorial serif, dark mode, quiet confidence |

Choose your theme at registration. Change it anytime with `/rebuild`.

## Architecture

```
[Notes App] → POST /publish → FastAPI (FastAPI Cloud)
                                 ├── SELECT token → Neon (one row)
                                 ├── Parse Markdown
                                 ├── Render HTML (Jinja2)
                                 ├── Fetch taxonomy.json (GitHub API)
                                 ├── Update taxonomy
                                 └── Push commit (post + source + index + taxonomy)
                                     → GitHub Pages (static output)
                                     → Return permalink
                                     → Die
```

The server holds nothing. The database holds one row per user. The content lives in the user's repo. The reader hits GitHub Pages directly. The pipeline is a matchstick — it lights, burns, and disappears.

## What This Is Not

This is not a SaaS. There is no subscription. There is no pricing page. There is no enterprise tier. There is no customer success manager. There is no roadmap driven by revenue targets.

This is a pipeline deployed on free infrastructure that does one thing: turn your Markdown into a blog post and get out of the way.

If you want to self-host, use the `main` branch with your own Leapcell, Docker, or bare-metal deployment. If you want to use the public instance, you're here.

## Clients

The protocol is four endpoints with a bearer token. Anything that speaks HTTP is a client.

| Client | Author | Status |
|--------|--------|--------|
| curl | You | Works now |
| [note2cms-publisher](https://github.com/garrul4ik/note2cms-publisher) | @garrul4ik | Obsidian plugin, v1.0.3 |
| iOS Shortcuts | You | 5 steps, zero code |
| Apple Notes → Share Sheet | You | Via Shortcuts |
| Your favorite HTTP client | You | POST JSON, get permalink |

## Cost

This instance runs on FastAPI Cloud's free tier with a Neon free-tier database. Total infrastructure cost: zero dollars.

Your blog runs on GitHub Pages. Total hosting cost: zero dollars.

A domain name costs twelve dollars a year.

Total cost of self-owned, beautifully themed, permanently archived, SaaSless publishing: **twelve dollars a year.**

---

## Standing on Shoulders

note2cms contains no original code. Every component was built by someone else, released with conviction, and composed into a pipeline. These are the people whose work makes this possible.

**Sebastian Ramirez** — FastAPI. The framework that gets out of the way. Four endpoints, async-native, type-hinted, zero bloat. The floor this building stands on. FastAPI Cloud — the platform this instance runs on. The framework author's own infrastructure, serving the framework's testament.

**Armin Ronacher** — Jinja2. The template engine that outlived the framework that made it famous. Released under BSD in 2008 because a template engine has no business being locked to a framework. Eighteen years later, it renders eight themes with visual flair on a CMS its author never imagined. A function: data in, HTML out. The purest tool in the stack.

**Tom Christie** — httpx. The async HTTP client that pushes static HTML to GitHub Pages. One `await client.put()` and a blog post is live on the internet. Also: Starlette, the ASGI framework underneath FastAPI. Also: Uvicorn, the server that runs it. Three foundational tools from one person.

**Samuel Colvin** — Pydantic. The validation layer that makes FastAPI's type hints work. note2cms validates one field: `markdown`. Pydantic does the least possible work for the best possible result. That's the highest compliment a validation library can receive.

**Charlie Marsh** — uv and Ruff. The package installer and linter that make Python fast. `fastapi deploy` installs seven dependencies in seconds because uv made dependency resolution a solved problem. The fastest build is the one with nothing to build.

**Marcelo Trylesinski** — Starlette and Uvicorn maintainer. The ASGI server that wakes, serves one publish request, and goes back to sleep. The infrastructure underneath the infrastructure.

**Eric S. Raymond** — "The Cathedral and the Bazaar." The philosophical framework that explains why a stranger built an Obsidian plugin overnight without asking permission. The bazaar model, described in 1997, proven in 2026.

**Guy Steele** — Scheme, the Jargon File, the Lambda Papers. The quiet architect who proved that a language can be tiny and powerful at the same time. The community of people who build small things that work together to create something big.

**Armin Ronacher** (again) — for investing in FastAPI Cloud. The creator of Flask funding the platform built on the framework that replaced Flask. No spite. Just infrastructure lifting infrastructure.

**@garrul4ik** — The first contributor. Built the Obsidian plugin overnight. Proved the bazaar forms around the protocol. Wrote a heroic Russian ode about the project's author, deployed on the Brutalist theme in monospace. The community that arrived before the community was planned.

---

## The Philosophy

I did not invent anything. I composed everything. The composition is the contribution.

Seven libraries. Seven maintainers. Each released with conviction under permissive licenses. Each does one thing, does it well, and does not care what calls it.

I gathered them behind four endpoints and pointed them at a specific problem: turning a note into a blog post without opening a browser.

The architecture is complete. I am afraid to add anything. The hardest commit is the one you do not make.

---

*The money is on the table. I can see it from here. I am not picking it up.*

## License

MIT. Issued with conviction, not from a dropdown menu.
