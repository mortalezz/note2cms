# Deployment Guide: Leapcell + GitHub Pages

*Total cost: $0 + domain name*

**Leapcell** hosts the FastAPI brain (4 endpoints, taxonomy DB).
**GitHub Pages** hosts the static body (the blog readers see).

---

## Architecture

```
[Your Notes App]
      │
      ▼ POST /publish (Bearer token)
┌─────────────────────────┐
│   Leapcell (free tier)  │
│                         │
│   FastAPI + PostgreSQL   │
│   ┌─────────────────┐   │
│   │ Pipeline 1: Build│──────► GitHub Pages (gh-pages branch)
│   │ Pipeline 2: Index│   │    ├── /posts/my-post/index.html
│   └─────────────────┘   │    ├── /posts/index.html
│                         │    └── (pure static HTML + CSS)
└─────────────────────────┘
      │
      ▼ Returns permalink
[Share with the world]
```

---

## Step 1: Create the GitHub Repository

```bash
# Create a new repo for your blog's static output
# Go to github.com/new → name it "blog" (or whatever you want)
# Enable GitHub Pages: Settings → Pages → Source: "Deploy from a branch"
# Branch: gh-pages, folder: / (root)

# Clone it locally (you'll need the repo URL later)
git clone https://github.com/YOUR_USERNAME/blog.git
cd blog
git checkout -b gh-pages
touch .nojekyll  # Tell GitHub Pages not to run Jekyll
echo "placeholder" > index.html
git add . && git commit -m "init" && git push origin gh-pages
```

Your blog will be live at: `https://YOUR_USERNAME.github.io/blog/`

---

## Step 2: Generate a GitHub Personal Access Token

1. Go to: github.com → Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. Create a new token with:
   - **Repository access**: Only select repositories → your blog repo
   - **Permissions**: Contents → Read and write
3. Copy the token — you'll need it for Leapcell environment variables

---

## Step 3: Create the Leapcell PostgreSQL Database

1. Log in to [leapcell.io](https://leapcell.io)
2. Click **Create Database**
3. Select PostgreSQL, pick a region close to you
4. Copy the connection string: `postgresql://user:pass@pooler.usXX.leap.cell/dbname`

---

## Step 4: Push note2cms to GitHub

```bash
# Fork or push the note2cms source to your GitHub account
git clone <your-note2cms-fork>
cd note2cms

# Make sure these files are present:
#   api/__init__.py (main FastAPI app)
#   api/main.py
#   pipeline/
#   themes/
#   vite-renderer/
#   requirements.txt
```

---

## Step 5: Deploy to Leapcell

1. Go to Leapcell Dashboard → **New Service**
2. Connect your GitHub account, select the note2cms repo
3. Configure:

| Field           | Value                                                     |
|-----------------|-----------------------------------------------------------|
| **Runtime**     | Python                                                    |
| **Build Command** | `pip install -r requirements.txt && cd vite-renderer && npm install` |
| **Start Command** | `uvicorn api.main:app --host 0.0.0.0 --port 8080`      |
| **Port**        | 8080                                                      |

4. Set **Environment Variables**:

| Variable          | Value                                                       |
|-------------------|-------------------------------------------------------------|
| `API_TOKEN`       | *(generate one: `python -c "import secrets; print(secrets.token_urlsafe(32))"`)* |
| `DATABASE_URL`    | `postgresql://user:pass@pooler.usXX.leap.cell/dbname`      |
| `SITE_TITLE`      | Your Blog Name                                              |
| `SITE_URL`        | `https://YOUR_USERNAME.github.io/blog`                      |
| `ACTIVE_THEME`    | `default`                                                   |
| `GITHUB_TOKEN`    | *(the PAT from Step 2)*                                     |
| `GITHUB_REPO`     | `YOUR_USERNAME/blog`                                        |
| `GITHUB_BRANCH`   | `gh-pages`                                                  |
| `DEPLOY_TARGET`   | `github_pages`                                              |

5. Click **Deploy**

---

## Step 6: Publish Your First Post

```bash
# Replace YOUR_LEAPCELL_URL with your *.leapcell.dev domain
# Replace YOUR_TOKEN with the API_TOKEN you generated

curl -X POST https://YOUR_LEAPCELL_URL/publish \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "markdown": "---\ntitle: Hello World\ntags: [first]\n---\n\nThis is my first post, published from the command line.\n\nThe browser is for consuming. I wrote this in my notes app."
  }'
```

You'll get back:
```json
{
  "permalink": "https://YOUR_USERNAME.github.io/blog/posts/hello-world/",
  "slug": "hello-world",
  "title": "Hello World",
  "created": true
}
```

Visit the permalink. Your post is live.

---

## Step 7: iOS Shortcut (Optional)

Create an iOS Shortcut that:
1. Receives shared text (from Notes, Bear, etc.)
2. Sends a POST request to `https://YOUR_LEAPCELL_URL/publish`
   - Headers: `Authorization: Bearer YOUR_TOKEN`, `Content-Type: application/json`
   - Body: `{"markdown": "[shared text]"}`
3. Extracts `permalink` from the JSON response
4. Copies to clipboard or opens in Safari

Now "Publish to Blog" appears in your share sheet. Done.

---

## Step 8: Custom Domain (When Ready)

1. Register a domain (e.g., `blog.yourdomain.com`)
2. In your blog GitHub repo: Settings → Pages → Custom domain → enter your domain
3. Set DNS: CNAME record pointing to `YOUR_USERNAME.github.io`
4. Update the `SITE_URL` environment variable on Leapcell
5. Wait for SSL certificate (automatic via GitHub)

---

## How It All Fits Together

- **You write** in Apple Notes, Bear, Obsidian, vim — wherever you think
- **You publish** via share sheet, curl, or any HTTP client
- **Leapcell** accepts the Markdown, builds HTML, updates taxonomy, pushes to GitHub
- **GitHub Pages** serves the static HTML globally via CDN
- **Readers** get pure HTML + CSS, no JavaScript, instant load
- **You own** the Markdown source, the taxonomy, and the static output

Total infrastructure: one free-tier Python runtime, one free PostgreSQL database,
one free GitHub Pages site. Your blog costs you a domain name and nothing else.

---

*Write where you think. Publish where they look. Own everything in between.*
