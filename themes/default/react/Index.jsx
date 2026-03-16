/**
 * Index.jsx — The blog index / post listing component.
 *
 * Shares visual DNA with Post.jsx — same fonts, colors, spacing.
 * Botanical coherence: these two files are one organism.
 *
 * Props:
 *   posts     — Array of { title, date, dateISO, tags, readingTime, slug, excerpt, permalink }
 *   siteTitle — Blog title from config (string)
 *   siteUrl   — Blog base URL from config (string)
 */

import React from "react";

export default function Index({ posts = [], siteTitle, siteUrl }) {
  return (
    <main className="index-container">
      <header className="index-header">
        <h1 className="index-title">{siteTitle}</h1>
        <p className="index-subtitle">Write where you think. Publish where they look. Own everything in between.</p>
      </header>

      {posts.length > 0 ? (
        <ul className="post-list">
          {posts.map((post) => (
            <li key={post.slug} className="post-item">
              <a href={post.permalink} className="post-item-link">
                <div className="post-item-meta">
                  <time dateTime={post.dateISO}>{post.date}</time>
                  <span className="sep" />
                  <span>{post.readingTime} min read</span>
                </div>
                <h2 className="post-item-title">{post.title}</h2>
                <p className="post-item-excerpt">{post.excerpt}</p>
                {post.tags.length > 0 && (
                  <div className="post-item-tags">
                    {post.tags.map((tag) => (
                      <span key={tag}>{tag}</span>
                    ))}
                  </div>
                )}
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <div className="empty-state">
          <p>No posts yet.</p>
          <p>Push some Markdown to get started.</p>
          <code>curl -X POST /publish</code>
        </div>
      )}
    </main>
  );
}
