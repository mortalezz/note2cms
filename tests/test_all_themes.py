"""Snapshot & safety smoke tests across all 21 themes."""

from pathlib import Path
import pytest

from pipeline.builder_cloud import CloudBuildPipeline
from pipeline.paginator import paginate_posts
from pipeline.parser import parse_markdown

THEMES_DIR = Path(__file__).parent.parent / "themes"
ALL_THEMES = sorted(
    d.name for d in THEMES_DIR.iterdir() if d.is_dir() and d.name != "_shared"
)


def _sample_posts(count: int) -> list[dict]:
    return [
        {
            "slug": f"post-{i}",
            "title": f'Post #{i} with "Quotes" & <Tags>',
            "date": f"2026-03-{(i % 28) + 1:02d}T12:00:00+00:00",
            "tags": ["python", "notes"] if i % 2 == 0 else ["travel"],
            "reading_time": 3,
            "excerpt": f'Excerpt with "double quotes" & <angle> #{i}',
            "series": "Caucasus" if i in (1, 2) else "",
            "series_order": i if i in (1, 2) else None,
        }
        for i in range(count, 0, -1)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("theme_name", ALL_THEMES)
async def test_all_themes_render_post_and_paginated_index(theme_name: str):
    assert len(ALL_THEMES) == 21

    for lang in ("en", "ru"):
        builder = CloudBuildPipeline(
            themes_dir=THEMES_DIR,
            active_theme=theme_name,
            site_title="Test Blog",
            site_url="https://example.com",
            site_lang=lang,
            enable_carousel=True,
            search_enabled=True,
        )
        await builder.initialize()

        # Render post with quotes in title/excerpt, carousel, series, tags, prev/next, related
        md_raw = (
            "---\n"
            'title: Post with "Quotes" & <Brackets>\n'
            "date: 2026-03-16\n"
            "tags: [python, notes]\n"
            "series: Caucasus\n"
            "series_order: 2\n"
            'excerpt: Safe "excerpt" <test>\n'
            "---\n\n"
            "![One](https://example.com/1.jpg)\n"
            "![Two](https://example.com/2.jpg)\n\n"
            "Body paragraph."
        )
        parsed = parse_markdown(md_raw)
        posts_47 = _sample_posts(47)
        rel = builder.compute_post_relations(
            "post-2", posts_47, tags=parsed.tags, series_name=parsed.series
        )
        bundle = builder.render_post_bundle(
            parsed,
            nav_pages=[{"slug": "about", "title": "About", "permalink": "https://example.com/posts/about/"}],
            **rel,
        )

        # HTML escaping in meta tags (no broken attribute quotes)
        assert ('&#34;Quotes&#34;' in bundle.html or '&quot;Quotes&quot;' in bundle.html)
        assert ('&#34;excerpt&#34;' in bundle.html or '&quot;excerpt&quot;' in bundle.html)
        assert f'<html lang="{lang}">' in bundle.html
        assert 'class="n2c-carousel"' in bundle.html
        assert 'class="n2c-series"' in bundle.html
        assert 'class="n2c-post-nav"' in bundle.html
        assert 'class="n2c-related"' in bundle.html
        assert 'class="n2c-share-bar"' in bundle.html
        assert 'class="n2c-share-btn n2c-share-native"' in bundle.html
        assert 'class="n2c-share-btn n2c-share-copy"' in bundle.html
        assert "/posts/tags/python/" in bundle.html
        assert bundle.og_image_url == "https://example.com/1.jpg"
        assert bundle.og_png_bytes is None

        # Static page must not render share bar or pinned meta
        page_post = parse_markdown("---\ntitle: About\ntype: page\npinned: true\n---\n\nStatic page body.")
        page_bundle = builder.render_post_bundle(page_post)
        assert 'class="n2c-share-bar"' not in page_bundle.html
        assert 'name="n2c:pinned"' not in page_bundle.html

        # Pinned post renders meta marker and full card on index, compact banner on archive & tag pages
        pinned_sample = parse_markdown("---\ntitle: Pinned Post\npinned: true\n---\n\nPinned body.")
        pinned_bundle = builder.render_post_bundle(pinned_sample)
        assert '<meta name="n2c:pinned" content="true">' in pinned_bundle.html
        assert 'class="n2c-share-bar"' in pinned_bundle.html

        # Also verify OG PNG card generation when post has no images
        text_only = parse_markdown("---\ntitle: Text Only Card\ntags: [notes]\n---\n\nJust words.")
        text_bundle = builder.render_post_bundle(text_only)
        assert text_bundle.og_png_bytes is not None
        assert len(text_bundle.og_png_bytes) > 1000

        # Non-brutalist2 themes must contain zero <script> on post pages
        if theme_name != "brutalist2":
            assert "<script" not in bundle.html.lower()

        # Paginated index checks for 1, 10, 11, 47 posts
        for n in (1, 10, 11, 47):
            sample_posts = _sample_posts(n)
            sample_posts[-1]["pinned"] = True
            slices = paginate_posts(
                sample_posts, per_page=10, mode="stable", base_url="https://example.com"
            )
            pinned_item = sample_posts[-1]
            idx_html = builder.render_index_slice(slices[-1], pinned_post=pinned_item)
            assert f'<html lang="{lang}">' in idx_html
            assert ('&#34;Quotes&#34;' in idx_html or '&quot;Quotes&quot;' in idx_html)
            assert 'class="n2c-site-nav"' in idx_html
            assert 'n2c-nav-spacer' not in idx_html
            assert 'justify-content: center;' in idx_html
            assert 'min-height: 44px;' in idx_html
            if theme_name in {
                "brutalist",
                "brutalist2",
                "darkroom",
                "ink",
                "manuscript",
                "swiss",
                "terminal",
                "vaporwave",
            }:
                assert '<div class="index-section">' in idx_html
            assert 'class="n2c-pinned-card"' in idx_html
            assert 'class="n2c-pinned-compact"' not in idx_html
            if n > 10:
                assert 'class="n2c-pagination"' in idx_html
                arch_html = builder.render_index_slice(slices[0], pinned_post=pinned_item)
                assert 'class="n2c-pinned-compact"' in arch_html
                assert 'class="n2c-pinned-card"' not in arch_html
            tag_html = builder.render_index_slice(
                slices[-1], active_tag="python", pinned_post=pinned_item
            )
            assert 'class="n2c-pinned-compact"' in tag_html
            assert 'class="n2c-pinned-card"' not in tag_html
            if theme_name != "brutalist2":
                assert "<script" not in idx_html.lower()

        # Tags overview & search page
        tags_html = builder.render_tags_overview({"python": 5, "travel": 3})
        assert "#python" in tags_html
        search_html = builder.render_search_page()
        assert 'id="n2c-search-input"' in search_html
