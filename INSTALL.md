# Installation Guide

Deploy your own note2cms blog for free. Total time: about 15 minutes.

**What you'll have when done:** A blog where you push Markdown from your phone or terminal and get a live, beautifully formatted permalink back. Total cost: $0 (plus a domain name if you want one later).

---

## What You Need Before Starting

- A **GitHub account** — [sign up here](https://github.com/signup) if you don't have one
- A **Leapcell account** — [sign up here](https://leapcell.io) (free tier, no credit card)
- A **terminal** — Terminal.app on Mac, any terminal on Linux, PowerShell on Windows
- **git** installed — [instructions here](https://git-scm.com/downloads) if you don't have it

That's it. No Node.js, no Python, no Docker on your machine. Everything runs in the cloud.

---

## Step 1: Fork the note2cms Repository

1. Go to [github.com/mortalezz/note2cms](https://github.com/mortalezz/note2cms)
2. Click the **Fork** button in the top right
3. This creates a copy of note2cms under your GitHub account

You now have `github.com/YOUR_USERNAME/note2cms`.

---

## Step 2: Create a Blog Repository

This is where your published blog posts will live as static HTML files.

1. Go to [github.com/new](https://github.com/new)
2. Name it `blog` (or whatever you want your blog URL to be)
3. Make it **Public**
4. **Do NOT** add a README, .gitignore, or license — keep it completely empty
5. Click **Create repository**

Now set up the blog branch. In your terminal:

```bash
cd /tmp
mkdir blog && cd blog
git init
git checkout -b gh-pages
touch .nojekyll
echo '<!DOCTYPE html><html><body><p>Coming soon.</p></body></html>' > index.html
git add .
git commit -m "init"
git remote add origin git@github.com:YOUR_USERNAME/blog.git
git push -u origin gh-pages
```

Replace `YOUR_USERNAME` with your actual GitHub username.

Now enable GitHub Pages:

1. Go to your blog repo on GitHub: `github.com/YOUR_USERNAME/blog`
2. Click **Settings** (gear icon)
3. In the left sidebar, click **Pages**
4. Under **Source**, select **Deploy from a branch**
5. Set branch to `gh-pages`, folder to `/ (root)`
6. Click **Save**

Wait a minute, then visit `https://YOUR_USERNAME.github.io/blog/`. You should see "Coming soon."

---

## Step 3: Generate a GitHub Access Token

note2cms needs permission to push built HTML files to your blog repo.

1. Go to [github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new)
2. **Token name**: `note2cms-deployer`
3. **Expiration**: 90 days (you can renew it later)
4. **Repository access**: click "Only select repositories" → select your `blog` repo
5. **Permissions**: expand "Repository permissions" → find **Contents** → set to **Read and write**
6. Click **Generate token**
7. **Copy the token immediately** — you won't see it again. Save it somewhere safe.

This token starts with `github_pat_`. Keep it — you'll use it in Step 5.

---

## Step 4: Create the Leapcell Database

1. Log in to [leapcell.io](https://leapcell.io)
2. Click **Create Database** (or find it in the dashboard)
3. Select **PostgreSQL**
4. Pick a region (US East or US West if you're in the US)
5. Give it a name like `note2cms`
6. Click **Create**

Once created, you'll see connection details. Find the **PostgreSQL URI** — it looks like:

```
postgresql://username:password@hostname:6438/dbname?sslmode=require
```

**Copy this entire URI.** You'll need it in the next step.

---

## Step 5: Deploy note2cms to Leapcell

This is the main step — you're putting the API server in the cloud.

1. Go to your Leapcell Dashboard → click **New Service**
2. Connect your GitHub account if prompted
3. Select your forked `note2cms` repository
4. Configure the service:

| Setting | Value |
|---|---|
| **Runtime** | Python |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn api.main:app --host 0.0.0.0 --port 8080` |
| **Port** | `8080` |

5. Now set the **Environment Variables**. This is the most important part.

First, generate your secret API token. In your terminal, run:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

If you don't have Python installed, use any random string generator — you need a long random string (32+ characters).

Now add these environment variables in Leapcell:

| Variable | What to put | Where it came from |
|---|---|---|
| `API_TOKEN` | Your generated random string | The command above |
| `DATABASE_URL` | The PostgreSQL URI | Step 4 |
| `SITE_TITLE` | Your blog's name (e.g., "My Blog") | You choose |
| `SITE_URL` | `https://YOUR_USERNAME.github.io/blog` | Step 2 (no trailing slash!) |
| `ACTIVE_THEME` | `default` | Just type this |
| `GITHUB_TOKEN` | The `github_pat_...` token | Step 3 |
| `GITHUB_REPO` | `YOUR_USERNAME/blog` | Step 2 |
| `GITHUB_BRANCH` | `gh-pages` | Just type this |
| `DEPLOY_TARGET` | `github_pages` | Just type this |

**Important:** Replace `YOUR_USERNAME` with your actual GitHub username in `SITE_URL` and `GITHUB_REPO`.

**Important:** `SITE_URL` must NOT have a trailing slash. Use `https://yourname.github.io/blog` not `https://yourname.github.io/blog/`.

6. Click **Deploy**

Watch the build logs. You should see:
- `pip install` succeeding
- `[taxonomy] Using PostgreSQL`
- `[deploy] GitHub Pages → YOUR_USERNAME/blog@gh-pages`
- `Uvicorn running on http://0.0.0.0:8080`

Once it's green, Leapcell gives you a URL like `something.leapcell.dev`. That's your API endpoint. **Save this URL.**

---

## Step 6: Publish Your First Post

Open your terminal and run (replace the two placeholder values):

```bash
curl -X POST https://YOUR_LEAPCELL_URL/publish \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "markdown": "---\ntitle: Hello World\ntags: [first]\n---\n\nThis is my first post, published from the command line.\n\nThe browser is for consuming. I wrote this in my notes app."
  }'
```

You should get back:

```json
{
  "permalink": "https://YOUR_USERNAME.github.io/blog/posts/hello-world/",
  "slug": "hello-world",
  "title": "Hello World",
  "created": true
}
```

Wait 30-60 seconds for GitHub Pages to update, then **open that permalink in your browser**.

Your first blog post is live on the internet.

---

## Step 7: Publish From a File

For longer posts, write Markdown in any text editor and publish from a file:

1. Create a file called `my-post.md`:

```markdown
---
title: My Second Post
tags: [thoughts, writing]
---

Write your content here in Markdown. Use headers, bold, italic,
code blocks, blockquotes — everything Markdown supports.

## A Section

More content here.

> A blockquote looks like this.
```

2. Publish it:

```bash
jq -Rs '{markdown: .}' my-post.md | curl -X POST \
  https://YOUR_LEAPCELL_URL/publish \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @-
```

If you don't have `jq` installed:
- **Mac**: `brew install jq`
- **Linux**: `sudo apt install jq`
- **Windows**: download from [jqlang.github.io/jq](https://jqlang.github.io/jq/download/)

---

## Step 8: Set Up iOS Shortcut (Optional)

If you want to publish from your iPhone or iPad:

1. Open the **Shortcuts** app
2. Create a new Shortcut
3. Add these actions:
   - **Receive** input from Share Sheet (Text)
   - **Get Contents of URL**:
     - URL: `https://YOUR_LEAPCELL_URL/publish`
     - Method: POST
     - Headers: `Authorization: Bearer YOUR_API_TOKEN` and `Content-Type: application/json`
     - Request Body (JSON): key `markdown`, value: Shortcut Input
   - **Get Dictionary Value**: key `permalink`
   - **Copy to Clipboard**
4. Name it "Publish to Blog"

Now when you write a note in Apple Notes or Bear, select the text, tap Share, and tap "Publish to Blog." The permalink is copied to your clipboard.

---

## Editing a Post

Get your original Markdown back:

```bash
curl https://YOUR_LEAPCELL_URL/posts/hello-world/source \
  -H "Authorization: Bearer YOUR_API_TOKEN"
```

Edit it, then publish again with the same title/slug. The post updates in place.

---

## Deleting a Post

```bash
curl -X DELETE https://YOUR_LEAPCELL_URL/posts/hello-world \
  -H "Authorization: Bearer YOUR_API_TOKEN"
```

Gone from the blog, gone from the database, gone from GitHub Pages.

---

## Adding a Custom Domain (Optional)

When you're ready for your own domain:

1. Buy a domain (Namecheap, Cloudflare, Google Domains — wherever)
2. In your blog repo on GitHub: **Settings → Pages → Custom domain** → enter your domain
3. At your DNS provider, add a CNAME record:
   - Name: `blog` (or `@` for root domain)
   - Target: `YOUR_USERNAME.github.io`
4. Wait for DNS propagation (up to 24 hours, usually faster)
5. Update `SITE_URL` in your Leapcell environment variables to your new domain
6. Republish a post to rebuild all links

GitHub automatically provisions an SSL certificate for your custom domain.

---

## Troubleshooting

**"Frontmatter must include 'title'"**
Your Markdown file must start with a YAML frontmatter block. The very first line must be `---`, followed by at least `title: Your Title`, followed by another `---`. No blank lines before the first `---`.

**Post published but permalink shows 404**
GitHub Pages takes 30-60 seconds to deploy. Wait a minute and refresh.

**Links on the index page go to wrong URL**
Check that `SITE_URL` in Leapcell has no trailing slash and includes the correct path (e.g., `/blog`).

**500 error on publish**
Check the Leapcell logs (Dashboard → your service → Logs). Common causes:
- Database connection string is wrong — verify `DATABASE_URL`
- GitHub token expired — generate a new one in Step 3
- Missing environment variable — verify all 9 variables from Step 5

**Service shows "unavailable"**
The Leapcell free tier may cold-start. Wait 10-15 seconds and retry the request.

---

## What You Own

After completing this guide, you have:

- **Your words** in a PostgreSQL database (and retrievable as original Markdown)
- **Your blog** as static HTML on GitHub Pages, served globally via CDN
- **Your API** running on Leapcell's free tier
- **Your code** forked on GitHub, modifiable at any time

No platform owns your content. No company can enshittify your blog. Everything is portable, replaceable, and under your control.

**Total cost: $0** (plus ~$12/year if you add a custom domain)

---

*Write where you think. Publish where they look. Own everything in between.*
