# Deployment Guide: FastAPI Cloud + Neon + GitHub Pages

*Total cost: $0*

- **FastAPI Cloud** (`fastapicloud.com`) hosts the FastAPI backend.
- **Neon** (`neon.tech`) hosts the serverless PostgreSQL taxonomy & markdown source database.
- **GitHub Pages** (`gh-pages` branch) hosts the static HTML blog.
- **Obsidian (`note2cms-publisher`)** sends notes to FastAPI Cloud in one click.

---

## Architecture

```
[Obsidian Note]
      │
      ▼ POST /publish (Bearer token)
┌──────────────────────────────────────────────┐
│            FastAPI Cloud (Serverless)        │
│                                              │
│   FastAPI Engine                             │
│   ├── Pipeline 1: Render HTML ───────────────┼──► GitHub Pages (gh-pages)
│   └── Pipeline 2: Upsert Taxonomy & Source   │     ├── /posts/my-post/index.html
└──────────────────────┬───────────────────────┘     └── index.html
                       │
                       ▼ PostgreSQL (DATABASE_URL)
┌──────────────────────────────────────────────┐
│           Neon Serverless PostgreSQL         │
│  - posts (taxonomy, tags, reading time)      │
│  - markdown_source (raw markdown backup)     │
└──────────────────────────────────────────────┘
```

---

## Step 1: Create the GitHub Repository (Blog Output)

1. Create a repository on GitHub (e.g., `blog`)
2. Enable GitHub Pages:
   - Go to repo **Settings** → **Pages**
   - Source: **Deploy from a branch**
   - Branch: `gh-pages` / `/ (root)`
3. Ensure the branch has an initial file (or run locally):
   ```bash
   git checkout -b gh-pages
   touch .nojekyll
   echo "placeholder" > index.html
   git add . && git commit -m "init" && git push origin gh-pages
   ```

---

## Step 2: Generate a GitHub Personal Access Token (PAT)

1. Go to GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)** or **Fine-grained**.
2. Permissions:
   - Repository access: your `blog` repo
   - Permissions: **Contents** (Read and write)
3. Copy the token (starts with `github_pat_` or `ghp_`).

---

## Step 3: Connect Neon PostgreSQL to FastAPI Cloud

1. In **FastAPI Cloud** (`fastapicloud.com`), go to your Project/Workspace settings.
2. Under **Integrations**, connect **Neon** (or create a database at [neon.tech](https://neon.tech)).
3. Copy the PostgreSQL connection string (`DATABASE_URL`), which looks like:
   `postgresql://username:password@ep-xyz.region.neon.tech/neondb?sslmode=require`

---

## Step 4: Deploy note2cms to FastAPI Cloud

1. In terminal, navigate to the `note2cms` directory:
   ```bash
   cd c:\_dev\note2cms
   ```
2. Log in to FastAPI Cloud (if not already logged in):
   ```bash
   fastapi login
   ```
3. Deploy the application:
   ```bash
   fastapi deploy
   ```
4. In the FastAPI Cloud dashboard, set the **Environment Variables**:

| Variable | Description / Value |
|---|---|
| `API_TOKEN` | A secret token for publishing (e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`) |
| `DATABASE_URL` | Neon PostgreSQL URI from Step 3 |
| `SITE_TITLE` | Your blog name (e.g., `stenAgram`) |
| `SITE_URL` | `https://YOUR_USERNAME.github.io/blog` (no trailing slash!) |
| `ACTIVE_THEME` | `default` |
| `GITHUB_TOKEN` | GitHub PAT from Step 2 |
| `GITHUB_REPO` | `YOUR_USERNAME/blog` |
| `GITHUB_BRANCH` | `gh-pages` |
| `DEPLOY_TARGET` | `github_pages` |

FastAPI Cloud will provide your live backend URL (e.g., `https://note2cms-xxxx.fastapicloud.dev`).

---

## Step 5: Migrate Existing Posts from GitHub Pages (One-time)

If you have already published posts on GitHub Pages and need to restore them into Neon PostgreSQL:

```bash
cd c:\_dev\note2cms
python migrate_from_blog.py --repo "YOUR_USERNAME/blog" --database-url "postgresql://..." --save-markdown ./content
```

This will automatically:
- Download all posts from `gh-pages`.
- Extract metadata and reconstruct clean Markdown with YAML frontmatter.
- Populate the `posts` and `markdown_source` tables in your Neon PostgreSQL database.
- Save local `.md` backups to `./content/`.

---

## Step 6: Configure Obsidian Plugin (`note2cms-publisher`)

1. Open Obsidian **Settings** → **note2cms Publisher**.
2. Set:
   - **API URL**: Your FastAPI Cloud URL (e.g., `https://note2cms-xxxx.fastapicloud.dev`)
   - **API Token**: The `API_TOKEN` set in FastAPI Cloud environment variables.
3. Click **Test connection** — you should see a green success notification!
4. Open any note and run **"Publish current note"** (or use **"Manage published posts"** to view restored posts).
