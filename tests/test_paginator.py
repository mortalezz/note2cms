"""Tests for stable and classic pagination and O(1) incremental slicing."""

from pipeline.paginator import paginate_posts, select_incremental_slices


def _make_posts(n: int) -> list[dict]:
    # Newest first: post-n .. post-1
    return [
        {
            "slug": f"post-{i:04d}",
            "title": f"Post {i}",
            "date": f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}+00:00",
            "tags": ["test"],
            "reading_time": 1,
            "excerpt": f"Excerpt {i}",
        }
        for i in range(n, 0, -1)
    ]


def test_paginate_empty_and_single_page():
    empty = paginate_posts([], per_page=10, mode="stable", base_url="https://example.com")
    assert len(empty) == 1
    assert empty[0].is_index is True
    assert empty[0].posts == []

    ten = paginate_posts(_make_posts(10), per_page=10, mode="stable")
    assert len(ten) == 1
    assert ten[0].posts[0]["slug"] == "post-0010"
    assert ten[0].posts[-1]["slug"] == "post-0001"


def test_stable_mode_preserves_archive_page_1_forever():
    slices_11 = paginate_posts(_make_posts(11), per_page=10, mode="stable")
    slices_47 = paginate_posts(_make_posts(47), per_page=10, mode="stable")

    # page/1 always contains posts 10..1 (oldest 10, shown newest-first on that page)
    assert [p["slug"] for p in slices_11[0].posts] == [f"post-{i:04d}" for i in range(10, 0, -1)]
    assert [p["slug"] for p in slices_47[0].posts] == [f"post-{i:04d}" for i in range(10, 0, -1)]
    assert slices_47[0].url == "/posts/page/1/"
    assert slices_47[-1].is_index is True
    assert slices_47[-1].url == "/posts/"
    assert [p["slug"] for p in slices_47[-1].posts] == [f"post-{i:04d}" for i in range(47, 40, -1)]


def test_classic_mode_orders_from_newest():
    slices = paginate_posts(_make_posts(25), per_page=10, mode="classic")
    assert len(slices) == 3
    assert slices[0].is_index is True
    assert slices[0].url == "/posts/"
    assert [p["slug"] for p in slices[0].posts] == [f"post-{i:04d}" for i in range(25, 15, -1)]
    assert slices[2].url == "/posts/page/3/"
    assert [p["slug"] for p in slices[2].posts] == [f"post-{i:04d}" for i in range(5, 0, -1)]


def test_stable_incremental_1000_posts_max_3_html_files():
    # Publishing post #1001 crosses page boundary 100 -> 101 pages
    posts_1001 = _make_posts(1001)
    slices = paginate_posts(posts_1001, per_page=10, mode="stable")
    inc_boundary = select_incremental_slices(
        slices, mode="stable", per_page=10, is_new_newest=True, total_after=1001
    )
    html_files_boundary = sum(len(s.output_paths) for s in inc_boundary)
    assert len(inc_boundary) == 2
    # Newly frozen page/100 + index (posts/index.html + index.html) == 3 HTML files
    assert html_files_boundary <= 3

    # Publishing post #1002 stays on the same index page
    posts_1002 = _make_posts(1002)
    slices2 = paginate_posts(posts_1002, per_page=10, mode="stable")
    inc_normal = select_incremental_slices(
        slices2, mode="stable", per_page=10, is_new_newest=True, total_after=1002
    )
    html_files_normal = sum(len(s.output_paths) for s in inc_normal)
    assert len(inc_normal) == 1
    assert html_files_normal == 2
