# Theming Guide

A theme is two HTML files. That's it.

## How Themes Work

note2cms ships with two themes:

- **default** — warm serif typography, Newsreader font, editorial feel, dark mode support
- **swiss** — Swiss Modernist / Bauhaus inspired, uppercase grid typography, primary color accents, geometric elements

Your active theme is set by the `ACTIVE_THEME` environment variable. Changing it and redeploying switches your entire blog's visual identity.

## Switching Themes

1. In your Leapcell dashboard (or `.env` file for self-hosted), change `ACTIVE_THEME`:
   ```
   ACTIVE_THEME=swiss
   ```

2. **Redeploy** the service (Leapcell: "Save and Rebuild" button)

3. Rebuild all posts with the new theme:
   ```bash
   curl -X POST https://YOUR_LEAPCELL_URL/rebuild \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

4. Done. Every post is now rendered with the new theme.

To switch back, change `ACTIVE_THEME` to `default`, redeploy, rebuild.

## Creating Your Own Theme

A theme lives in `themes/your-theme-name/` and contains exactly two files:

```
themes/
└── your-theme-name/
    ├── post.html      ← renders a single blog post
    └── index.html     ← renders the post listing page
```

Both are Jinja2 templates. If you've ever written HTML, you can write a theme.

### post.html

Your post template receives these variables:

| Variable | Type | Example |
|---|---|---|
| `title` | string | `"My Post Title"` |
| `date` | string | `"March 16, 2026"` |
| `date_iso` | string | `"2026-03-16T12:00:00+00:00"` |
| `content` | HTML string | `"<p>Your rendered Markdown...</p>"` |
| `tags` | list of strings | `["philosophy", "code"]` |
| `reading_time` | integer | `4` |
| `slug` | string | `"my-post-title"` |
| `excerpt` | string | `"First paragraph of the post..."` |
| `site_title` | string | `"My Blog"` |
| `site_url` | string | `"https://example.github.io/blog"` |

Minimal example:

```html
<!DOCTYPE html>
<html>
<head>
    <title>{{ title }} — {{ site_title }}</title>
</head>
<body>
    <h1>{{ title }}</h1>
    <time>{{ date }}</time>
    <span>{{ reading_time }} min read</span>

    <article>
        {{ content }}
    </article>

    <a href="{{ site_url }}/posts/">← All posts</a>
</body>
</html>
```

The `{{ content }}` variable contains your Markdown already rendered as HTML — paragraphs, headers, code blocks, blockquotes, lists, tables, everything. Your theme just wraps it in whatever design you want.

### index.html

Your index template receives these variables:

| Variable | Type | Description |
|---|---|---|
| `posts` | list of dicts | All posts, newest first |
| `site_title` | string | Your blog name |
| `site_url` | string | Your blog URL |

Each post in the `posts` list contains:

| Key | Type | Example |
|---|---|---|
| `title` | string | `"My Post Title"` |
| `display_date` | string | `"March 16, 2026"` |
| `date` | string | ISO date |
| `tags` | list of strings | `["philosophy", "code"]` |
| `reading_time` | integer | `4` |
| `slug` | string | `"my-post-title"` |
| `excerpt` | string | `"First paragraph..."` |
| `permalink` | string | Full URL to the post |

Minimal example:

```html
<!DOCTYPE html>
<html>
<head>
    <title>{{ site_title }}</title>
</head>
<body>
    <h1>{{ site_title }}</h1>

    {% for post in posts %}
    <article>
        <a href="{{ post.permalink }}">
            <h2>{{ post.title }}</h2>
        </a>
        <time>{{ post.display_date }}</time>
        <p>{{ post.excerpt }}</p>
    </article>
    {% endfor %}
</body>
</html>
```

That's a complete, working theme. Everything else — fonts, colors, layout, animations, geometric decorations — is CSS you add to make it yours.

## Tips

**Fonts.** Google Fonts works great — just add a `<link>` or `@import` in your `<head>`. The default theme uses Newsreader, the Swiss theme uses Instrument Sans.

**Dark mode.** Use `@media (prefers-color-scheme: dark)` with CSS variables. See `themes/default/post.html` for an example.

**OG tags.** Add Open Graph meta tags so your posts look good when shared on social media:
```html
<meta property="og:title" content="{{ title }}">
<meta property="og:description" content="{{ excerpt }}">
<meta property="og:type" content="article">
```

**No JavaScript required.** Your theme outputs static HTML. You can add JS if you want (analytics, animations), but the reader doesn't need it. Keep it light.

**Test locally.** Self-host note2cms on your machine, set `ACTIVE_THEME=your-theme-name`, publish a test post, open the HTML in your browser. Iterate until it looks right, then push.

## Contributing Themes

Built a theme you're proud of? Add it to `themes/your-theme-name/` and open a pull request. The community can switch to it with one environment variable.

Every theme is two files. Every theme uses the same variables. Every theme produces static HTML. The pipeline doesn't care what your CSS looks like. Go wild.
