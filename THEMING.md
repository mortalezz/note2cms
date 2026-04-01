# Theming Guide

A theme is two HTML files. One personality. Zero JavaScript.

## The Three Layers

A note2cms theme operates on three layers:

**Layer 1: Data Contract** — the theme receives props (title, date, content, tags) and returns HTML. This is the functional layer. Every theme system has this. It is necessary and it is boring.

**Layer 2: Visual Identity** — fonts, colors, spacing, layout. The static appearance when the page loads. This is what most theme systems consider the entire job.

**Layer 3: Behavioral Signature** — the one trick. A hidden visual flair that rewards interaction. A hover state that surprises. A load animation that sets the mood. This is what no other theme system provides, and it is what makes the difference between a page that exists and a page that someone remembers.

When building a theme, think about all three layers. The third one is what makes yours unforgettable.

## Available Themes

note2cms ships with eight themes. Each has a distinct personality and a hidden trick.

| Theme | Aesthetic | The Trick |
|---|---|---|
| `default` | Warm editorial serif, Newsreader on parchment | Dark mode via `prefers-color-scheme` — the first theme, the one that proves the concept |
| `swiss` | Bauhaus geometry, Instrument Sans, primary colors, rigid grid | Numbered post counter in the index, red/blue/yellow geometric accents as fixed elements |
| `brutalist` | IBM Plex Mono, 4px black borders, zero decoration | Binary hover inversion — entire index rows flip black-to-white instantly, no transition |
| `terminal` | Fira Code, phosphor green on dark, CRT scanlines | Headers prefixed with `##`, footer says `$ cd ../posts/`, scanline overlay via repeating gradient |
| `vaporwave` | Outfit font, pink-to-purple gradients, floating radial glows | Cards lift on hover with gradient title reveal and purple box shadow |
| `ink` | Cormorant Garamond, rice paper texture, vermillion accents | Brushstroke animation unfurls under the title on load; index titles get a pulsing ink dot on hover |
| `darkroom` | Source Serif, amber safelight on deep black, vignette | Images "develop" like photographs — start dark with sepia, fade into full visibility; h2 bars glow on hover |
| `manuscript` | Literata + Courier Prime, cream paper, red margin line | Section numbers appear in the margin like a reviewer's pencil marks; cursor changes to crosshair over links |

## Switching Themes

1. In your Leapcell dashboard (or `.env` for self-hosted), change `ACTIVE_THEME`:
   ```
   ACTIVE_THEME=darkroom
   ```

2. **Redeploy** the service (Leapcell: "Save and Rebuild" button)

3. Rebuild all posts with the new theme:
   ```bash
   curl -X POST https://YOUR_LEAPCELL_URL/rebuild \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

4. Done. Every post is now rendered with the new theme.

One environment variable. One curl. Whole blog redesigned.

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

That's a complete, working theme. Everything else — fonts, colors, layout, animations, the one trick — is CSS you add to make it yours.

## The Visual Flair Principle

When designing your theme's trick, follow this principle: **the trick must be earned by context.**

A hover effect on an already-animated page is noise. A hover effect on a deliberately still page is an event. The power of the trick comes from what the rest of the design chose not to do.

Guidelines:

**One trick per theme.** Two tricks compete. One trick defines. Pick the moment you want the reader to remember and design everything else to support it.

**CSS only.** No JavaScript. The trick must survive in static HTML served from a CDN. CSS animations, transitions, pseudo-elements, counters, and `prefers-color-scheme` are your toolkit. They are more than enough.

**Earn it through restraint.** If your theme is minimal, the trick should be the one moment of visual intensity. If your theme is bold, the trick should be the one moment of unexpected subtlety. The trick works by contrast with the design's baseline personality.

**Match the metaphor.** The Ink theme's trick is a brushstroke because the metaphor is calligraphy. The Darkroom's trick is a developing photograph because the metaphor is a darkroom. The Manuscript's trick is margin annotations because the metaphor is a reviewed paper. The trick should feel like it belongs to the world the theme creates.

**Test on mobile.** Some tricks (hover states) don't work on touch devices. That's fine — the trick is a bonus, not a requirement. The theme must be beautiful without the trick. The trick rewards desktop readers without punishing mobile ones.

## Dark Mode

If your theme has a light background, add dark mode support. Use CSS variables and `prefers-color-scheme`:

```css
:root {
    --ink: #1a1a1a;
    --paper: #faf9f7;
}

@media (prefers-color-scheme: dark) {
    :root {
        --ink: #e8e4df;
        --paper: #191816;
    }
}
```

All CSS that references `var(--ink)` and `var(--paper)` automatically switches. Dark-on-light themes (Terminal, Darkroom, Vaporwave) don't need this — they're already dark.

## Tips

**Fonts.** Google Fonts works great — add a `<link>` or `@import` in your `<style>`. Pair a distinctive display font with a readable body font. Avoid Inter, Roboto, and system defaults.

**OG tags.** Add Open Graph meta tags so posts look good when shared:
```html
<meta property="og:title" content="{{ title }}">
<meta property="og:description" content="{{ excerpt }}">
<meta property="og:type" content="article">
```

**No JavaScript required.** The reader doesn't need it. You can add analytics or progressive enhancement, but the page must be fully functional without it.

**Test locally.** Self-host note2cms, set `ACTIVE_THEME=your-theme-name`, publish a test post, iterate in the browser. When it's right, push and deploy.

## Contributing Themes

Built a theme you're proud of? Add it to `themes/your-theme-name/` and open a pull request. The community switches to it with one environment variable.

Two files. One personality. Zero JavaScript. Every bit of life considered. Go wild.
