#!/usr/bin/env node
/**
 * note2cms Vite/React Static Site Generator
 *
 * This is the production build pipeline. It:
 *   1. Reads Markdown source files from the content directory
 *   2. Parses frontmatter + converts MD to HTML via `marked`
 *   3. Server-side renders the theme's React components (Post.jsx / Index.jsx)
 *   4. Wraps the output in a full HTML shell with Vite-built CSS/JS assets
 *   5. Writes static HTML files to the output directory
 *
 * The theme contract:
 *   Post.jsx  — default export, receives: { title, date, dateISO, content, tags, readingTime, slug }
 *   Index.jsx — default export, receives: { posts: [{ title, date, dateISO, tags, readingTime, slug, excerpt, permalink }], siteTitle }
 *
 * Usage:
 *   node render.js                          # Build all posts + index
 *   node render.js --slug my-post           # Build one post + rebuild index
 *   node render.js --delete my-post         # Remove a post + rebuild index
 *   node render.js --index-only             # Rebuild just the index
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { marked } from "marked";
import matter from "gray-matter";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

// ---------------------------------------------------------------------------
// Config (mirrors Python-side .env)
// ---------------------------------------------------------------------------
const CONTENT_DIR = process.env.CONTENT_DIR || path.join(ROOT, "content");
const STATIC_DIR = process.env.STATIC_DIR || path.join(ROOT, "static");
const THEMES_DIR = process.env.THEMES_DIR || path.join(ROOT, "themes");
const ACTIVE_THEME = process.env.ACTIVE_THEME || "default";
const SITE_TITLE = process.env.SITE_TITLE || "My Blog";
const SITE_URL = process.env.SITE_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Markdown → structured post
// ---------------------------------------------------------------------------
function parseMarkdownFile(filePath) {
  const raw = fs.readFileSync(filePath, "utf-8");
  const { data: meta, content } = matter(raw);

  if (!meta.title) {
    throw new Error(`Missing 'title' in frontmatter: ${filePath}`);
  }

  const slug = meta.slug || slugify(meta.title);
  const dateStr = meta.date
    ? new Date(meta.date).toISOString()
    : new Date().toISOString();
  const displayDate = formatDate(dateStr);
  const tags = normalizeTags(meta.tags);
  const htmlContent = marked.parse(content);
  const readingTime = Math.max(1, Math.ceil(content.split(/\s+/).length / 220));
  const excerpt = meta.excerpt || extractExcerpt(content);

  return {
    title: meta.title,
    slug,
    date: displayDate,
    dateISO: dateStr,
    tags,
    content: htmlContent,
    readingTime,
    excerpt,
    permalink: `/posts/${slug}/`,
  };
}

function slugify(text) {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .substring(0, 80)
    .replace(/^-|-$/g, "");
}

function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function normalizeTags(tags) {
  if (!tags) return [];
  if (typeof tags === "string") return tags.split(",").map((t) => t.trim().toLowerCase());
  return tags.map((t) => String(t).trim().toLowerCase());
}

function extractExcerpt(content, maxChars = 200) {
  const clean = content
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/!\[.*?\]\(.*?\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[*_]{1,3}/g, "")
    .replace(/```[\s\S]*?```/g, "")
    .replace(/`[^`]+`/g, "");

  const paragraphs = clean.split(/\n\n+/).filter((p) => p.trim());
  if (!paragraphs.length) return "";

  let excerpt = paragraphs[0].trim();
  if (excerpt.length > maxChars) {
    excerpt = excerpt.substring(0, maxChars).replace(/\s\S*$/, "") + "\u2026";
  }
  return excerpt;
}

// ---------------------------------------------------------------------------
// Theme loading — compiles JSX via esbuild, then imports the result
// ---------------------------------------------------------------------------
import { buildSync } from "esbuild";

async function loadTheme() {
  const themePath = path.join(THEMES_DIR, ACTIVE_THEME, "react");

  // Compile into vite-renderer/.theme-cache/ — adjacent to node_modules
  // so bare "react" imports resolve naturally via Node's module resolution.
  const cacheDir = path.join(__dirname, ".theme-cache");
  fs.mkdirSync(cacheDir, { recursive: true });

  for (const component of ["Post", "Index"]) {
    buildSync({
      entryPoints: [path.join(themePath, `${component}.jsx`)],
      outfile: path.join(cacheDir, `${component}.mjs`),
      bundle: false,
      format: "esm",
      platform: "node",
      jsx: "automatic",
      jsxImportSource: "react",
    });
  }

  // Bust the import cache with a query string
  const cacheBust = `?t=${Date.now()}`;
  const postMod = await import(path.join(cacheDir, `Post.mjs${cacheBust}`));
  const indexMod = await import(path.join(cacheDir, `Index.mjs${cacheBust}`));

  return {
    Post: postMod.default,
    Index: indexMod.default,
  };
}

// ---------------------------------------------------------------------------
// HTML shell — wraps React SSR output in a full document
// ---------------------------------------------------------------------------
function htmlShell({ title, description, canonical, body, themeCSS }) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(title)}</title>
  <meta name="description" content="${escapeHtml(description)}">
  <meta property="og:title" content="${escapeHtml(title)}">
  <meta property="og:description" content="${escapeHtml(description)}">
  <meta property="og:type" content="article">
  ${canonical ? `<meta property="og:url" content="${canonical}">` : ""}
  ${canonical ? `<link rel="canonical" href="${canonical}">` : ""}
  <meta name="twitter:card" content="summary">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,500;1,6..72,300;1,6..72,400&family=JetBrains+Mono:wght@400;500&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
  ${themeCSS ? `<style>${themeCSS}</style>` : ""}
</head>
<body>
  <div id="root">${body}</div>
</body>
</html>`;
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---------------------------------------------------------------------------
// Build functions
// ---------------------------------------------------------------------------
function buildPost(post, PostComponent, themeCSS) {
  const element = createElement(PostComponent, {
    title: post.title,
    date: post.date,
    dateISO: post.dateISO,
    content: post.content,
    tags: post.tags,
    readingTime: post.readingTime,
    slug: post.slug,
    siteTitle: SITE_TITLE,
    siteUrl: SITE_URL,
  });

  const body = renderToString(element);

  const html = htmlShell({
    title: `${post.title} — ${SITE_TITLE}`,
    description: post.excerpt,
    canonical: `${SITE_URL}/posts/${post.slug}/`,
    body,
    themeCSS,
  });

  const outDir = path.join(STATIC_DIR, post.slug);
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, "index.html"), html, "utf-8");

  return outDir;
}

function buildIndex(posts, IndexComponent, themeCSS) {
  const sortedPosts = [...posts].sort(
    (a, b) => new Date(b.dateISO) - new Date(a.dateISO)
  );

  const element = createElement(IndexComponent, {
    posts: sortedPosts,
    siteTitle: SITE_TITLE,
    siteUrl: SITE_URL,
  });

  const body = renderToString(element);

  const html = htmlShell({
    title: SITE_TITLE,
    description: `${SITE_TITLE} — writing, published from notes.`,
    canonical: `${SITE_URL}/posts/`,
    body,
    themeCSS,
  });

  fs.mkdirSync(STATIC_DIR, { recursive: true });
  fs.writeFileSync(path.join(STATIC_DIR, "index.html"), html, "utf-8");
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------
async function main() {
  const args = process.argv.slice(2);
  const flags = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--slug" && args[i + 1]) flags.slug = args[++i];
    else if (args[i] === "--delete" && args[i + 1]) flags.delete = args[++i];
    else if (args[i] === "--index-only") flags.indexOnly = true;
  }

  // Load theme
  const theme = await loadTheme();

  // Load theme CSS
  const cssPath = path.join(THEMES_DIR, ACTIVE_THEME, "react", "theme.css");
  const themeCSS = fs.existsSync(cssPath)
    ? fs.readFileSync(cssPath, "utf-8")
    : "";

  // Handle delete
  if (flags.delete) {
    const outDir = path.join(STATIC_DIR, flags.delete);
    if (fs.existsSync(outDir)) {
      fs.rmSync(outDir, { recursive: true });
      console.log(`  ✓ Deleted ${flags.delete}`);
    }
    // Rebuild index without deleted post
    const posts = getAllPosts().filter((p) => p.slug !== flags.delete);
    buildIndex(posts, theme.Index, themeCSS);
    console.log(`  ✓ Index rebuilt (${posts.length} posts)`);
    return;
  }

  // Handle index-only rebuild
  if (flags.indexOnly) {
    const posts = getAllPosts();
    buildIndex(posts, theme.Index, themeCSS);
    console.log(`  ✓ Index rebuilt (${posts.length} posts)`);
    return;
  }

  // Handle single-slug build
  if (flags.slug) {
    const filePath = path.join(CONTENT_DIR, `${flags.slug}.md`);
    if (!fs.existsSync(filePath)) {
      console.error(`  ✗ ${flags.slug}.md not found in ${CONTENT_DIR}`);
      process.exit(1);
    }
    const post = parseMarkdownFile(filePath);
    buildPost(post, theme.Post, themeCSS);
    console.log(`  ✓ Built ${post.slug}`);

    // Rebuild index with all posts
    const posts = getAllPosts();
    buildIndex(posts, theme.Index, themeCSS);
    console.log(`  ✓ Index rebuilt (${posts.length} posts)`);
    return;
  }

  // Default: build everything
  const posts = getAllPosts();
  for (const post of posts) {
    buildPost(post, theme.Post, themeCSS);
    console.log(`  ✓ Built ${post.slug}`);
  }
  buildIndex(posts, theme.Index, themeCSS);
  console.log(`\n✓ Built ${posts.length} posts + index`);
}

function getAllPosts() {
  if (!fs.existsSync(CONTENT_DIR)) return [];
  return fs
    .readdirSync(CONTENT_DIR)
    .filter((f) => f.endsWith(".md"))
    .map((f) => parseMarkdownFile(path.join(CONTENT_DIR, f)))
    .sort((a, b) => new Date(b.dateISO) - new Date(a.dateISO));
}

main().catch((err) => {
  console.error("Build failed:", err);
  process.exit(1);
});
