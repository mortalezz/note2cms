/**
 * Post.jsx — The blog post component.
 *
 * This single file controls the entire visual identity of every post.
 * Change this file, change how your blog looks. That's the whole theming API.
 *
 * Props:
 *   title       — Post title (string)
 *   date        — Display date, e.g. "March 16, 2026" (string)
 *   dateISO     — ISO date for <time> datetime (string)
 *   content     — Rendered HTML from Markdown (string — injected via dangerouslySetInnerHTML)
 *   tags        — Array of tag strings
 *   readingTime — Estimated reading time in minutes (number)
 *   slug        — URL slug (string)
 *   siteTitle   — Blog title from config (string)
 *   siteUrl     — Blog base URL from config (string)
 */

import React from "react";

export default function Post({
  title,
  date,
  dateISO,
  content,
  tags = [],
  readingTime,
  slug,
  siteTitle,
  siteUrl,
}) {
  return (
    <React.Fragment>
      <article>
        <header className="post-header">
          <div className="post-meta">
            <time dateTime={dateISO}>{date}</time>
            <span className="sep" />
            <span>{readingTime} min read</span>
          </div>
          <h1 className="post-title">{title}</h1>
          {tags.length > 0 && (
            <div className="post-tags">
              {tags.map((tag) => (
                <span key={tag}>{tag}</span>
              ))}
            </div>
          )}
        </header>

        <div
          className="post-content"
          dangerouslySetInnerHTML={{ __html: content }}
        />
      </article>

      <footer className="post-footer">
        <a href={`${siteUrl}/posts/`}>
          <span className="arrow">←</span> All posts
        </a>
      </footer>
    </React.Fragment>
  );
}
