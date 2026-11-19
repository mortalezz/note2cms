"""Tests for Markdown parsing, UTC date normalization, and Windows-safe localization."""

import pytest

from pipeline.i18n import format_date, get_translations
from pipeline.parser import parse_markdown


def test_parse_minimal_frontmatter():
    raw = "---\ntitle: Hello Note\ntags: [Python, Web, python]\n---\n\nFirst paragraph **bold**.\n\nSecond paragraph."
    post = parse_markdown(raw)
    assert post.title == "Hello Note"
    assert post.slug == "hello-note"
    assert post.tags == ["python", "web"]
    assert post.excerpt == "First paragraph bold."
    assert post.reading_time == 1
    assert post.post_type == "post"
    assert post.carousel is True


def test_parse_extended_frontmatter_and_date_normalization():
    raw = (
        "---\n"
        "title: Elbrus Part 2\n"
        "date: 2026-03-16\n"
        "cover: hero.jpg\n"
        "series: Caucasus\n"
        "series_order: 2\n"
        "type: page\n"
        "carousel: false\n"
        "---\n\n"
        "::: gallery caption=\"Ignored in excerpt\"\n"
        "![[01.jpg]]\n"
        ":::\n\n"
        "Actual excerpt paragraph."
    )
    post = parse_markdown(raw)
    assert post.date.startswith("2026-03-16T00:00:00+00:00")
    assert post.cover == "hero.jpg"
    assert post.series == "Caucasus"
    assert post.series_order == 2
    assert post.post_type == "page"
    assert post.carousel is False
    assert post.excerpt == "Actual excerpt paragraph."


def test_parse_mixed_timezone_dates_sort_chronologically():
    p_early = parse_markdown("---\ntitle: Early\ndate: 2026-03-16T09:00:00+03:00\n---\nBody")
    p_late = parse_markdown("---\ntitle: Late\ndate: 2026-03-16T08:00:00+00:00\n---\nBody")
    # 09:00+03:00 is 06:00 UTC < 08:00 UTC
    assert p_early.date < p_late.date


def test_parse_missing_title_raises_value_error():
    with pytest.raises(ValueError, match="title"):
        parse_markdown("---\ntags: [a]\n---\nNo title")


def test_i18n_dates_and_labels_cross_platform():
    assert format_date("2026-03-05T12:00:00+00:00", "en") == "March 5, 2026"
    assert format_date("2026-03-05T12:00:00+00:00", "ru") == "5 марта 2026"
    assert get_translations("ru")["all_posts"] == "Все посты"
    assert get_translations("en")["all_posts"] == "All posts"
    assert get_translations("ru")["pinned_label"] == "Закреплено"
    assert get_translations("en")["pinned_label"] == "Pinned"
    assert get_translations("ru")["share_post"] == "Поделиться"
    assert get_translations("en")["share_post"] == "Share"
    # Unknown language falls back safely to English
    assert get_translations("xx")["min_read"] == "min read"


def test_parse_pinned_frontmatter_and_page_exclusion():
    p_pinned = parse_markdown("---\ntitle: Pinned\npinned: true\n---\nHello")
    assert p_pinned.pinned is True

    p_alias = parse_markdown("---\ntitle: Pin Alias\npin: yes\n---\nHello")
    assert p_alias.pinned is True

    p_false = parse_markdown("---\ntitle: Unpinned\npinned: false\n---\nHello")
    assert p_false.pinned is False

    p_page = parse_markdown("---\ntitle: About\ntype: page\npinned: true\n---\nBio")
    assert p_page.post_type == "page"
    assert p_page.pinned is False
