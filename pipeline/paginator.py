"""
Pagination engine for note2cms.

Supports two modes:
- `stable` (default): Archive pages are sliced from oldest to newest (`page/1` = oldest N posts).
  Old archive pages never shift when new posts are published, preserving O(1) builds and
  permanent URLs. The root/index page always displays the newest chunk.
- `classic`: Traditional newest-first slicing (`page/1` = index/newest, `page/2` = next older, ...).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PageItem:
    number: Optional[int]
    url: Optional[str]
    is_current: bool = False
    is_ellipsis: bool = False


@dataclass
class PageSlice:
    page_number: int
    total_pages: int
    posts: list[dict]
    url: str
    output_paths: list[str]
    prev_url: Optional[str]
    next_url: Optional[str]
    newer_url: Optional[str]
    older_url: Optional[str]
    pages: list[PageItem]
    is_index: bool = False


def _join_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    clean_path = "/" + path.lstrip("/")
    return f"{base}{clean_path}" if base else clean_path


def _windowed_numbers(current_pos: int, ordered_numbers: list[int], window: int = 2) -> list[Optional[int]]:
    """
    Build a compact list of page numbers with `None` representing an ellipsis.
    `ordered_numbers` is in display order (e.g., [5, 4, 3, 2, 1] or [1, 2, 3, 4, 5]).
    """
    total = len(ordered_numbers)
    if total <= 7:
        return list(ordered_numbers)

    keep_indices = {0, total - 1}
    for idx in range(max(0, current_pos - window), min(total, current_pos + window + 1)):
        keep_indices.add(idx)

    result: list[Optional[int]] = []
    prev_kept = -1
    for idx in sorted(keep_indices):
        if prev_kept != -1 and idx - prev_kept > 1:
            result.append(None)
        result.append(ordered_numbers[idx])
        prev_kept = idx
    return result


def paginate_posts(
    posts: list[dict],
    per_page: int = 10,
    mode: str = "stable",
    base_url: str = "",
    prefix: str = "/posts",
    include_root_index: bool = True,
) -> list[PageSlice]:
    """
    Slice newest-first `posts` into PageSlice objects.

    Args:
        posts: List of post dicts ordered newest-first.
        per_page: Maximum posts per page (>= 1).
        mode: "stable" (default) or "classic".
        base_url: Site base URL (e.g. "https://example.com" or "").
        prefix: URL prefix ("/posts" for main blog, "/posts/tags/python" for tag pages).
        include_root_index: When True and prefix == "/posts", also output root "index.html".
    """
    per_page = max(1, int(per_page))
    norm_mode = (mode or "stable").strip().lower()
    if norm_mode not in ("stable", "classic"):
        norm_mode = "stable"

    clean_prefix = prefix.strip("/")  # e.g. "posts" or "posts/tags/python"
    index_url = _join_url(base_url, f"/{clean_prefix}/")

    def _page_url(page_num: int, is_idx: bool) -> str:
        if is_idx:
            return index_url
        return _join_url(base_url, f"/{clean_prefix}/page/{page_num}/")

    def _index_outputs() -> list[str]:
        paths = [f"{clean_prefix}/index.html"]
        if include_root_index and clean_prefix == "posts":
            paths.append("index.html")
        return paths

    if not posts:
        return [
            PageSlice(
                page_number=1,
                total_pages=1,
                posts=[],
                url=index_url,
                output_paths=_index_outputs(),
                prev_url=None,
                next_url=None,
                newer_url=None,
                older_url=None,
                pages=[PageItem(number=1, url=index_url, is_current=True)],
                is_index=True,
            )
        ]

    if norm_mode == "classic":
        chunks = [posts[i:i + per_page] for i in range(0, len(posts), per_page)]
        total_pages = len(chunks)
        ordered_nums = list(range(1, total_pages + 1))

        slices: list[PageSlice] = []
        for idx, chunk in enumerate(chunks):
            page_num = idx + 1
            is_idx = page_num == 1
            url = _page_url(page_num, is_idx)
            outputs = _index_outputs() if is_idx else [f"{clean_prefix}/page/{page_num}/index.html"]
            newer_url = _page_url(page_num - 1, (page_num - 1) == 1) if page_num > 1 else None
            older_url = _page_url(page_num + 1, False) if page_num < total_pages else None

            win = _windowed_numbers(idx, ordered_nums)
            items = [
                PageItem(number=None, url=None, is_current=False, is_ellipsis=True)
                if num is None
                else PageItem(
                    number=num,
                    url=_page_url(num, num == 1),
                    is_current=(num == page_num),
                )
                for num in win
            ]

            slices.append(
                PageSlice(
                    page_number=page_num,
                    total_pages=total_pages,
                    posts=chunk,
                    url=url,
                    output_paths=outputs,
                    prev_url=newer_url,
                    next_url=older_url,
                    newer_url=newer_url,
                    older_url=older_url,
                    pages=items,
                    is_index=is_idx,
                )
            )
        return slices

    # --- Stable mode ---
    # Slice from oldest to newest so early pages (`page/1`, `page/2`, ...) freeze forever.
    oldest_first = list(reversed(posts))
    raw_chunks = [oldest_first[i:i + per_page] for i in range(0, len(oldest_first), per_page)]
    # Display posts newest-first within each page
    chunks = [list(reversed(c)) for c in raw_chunks]
    total_pages = len(chunks)

    # Display navigation newest-to-oldest (e.g., [total_pages, ..., 2, 1])
    ordered_nums = list(range(total_pages, 0, -1))

    slices = []
    for idx, chunk in enumerate(chunks):
        page_num = idx + 1
        is_idx = page_num == total_pages
        url = _page_url(page_num, is_idx)
        outputs = _index_outputs() if is_idx else [f"{clean_prefix}/page/{page_num}/index.html"]

        newer_url = _page_url(page_num + 1, (page_num + 1) == total_pages) if page_num < total_pages else None
        older_url = _page_url(page_num - 1, False) if page_num > 1 else None

        pos_in_display = ordered_nums.index(page_num)
        win = _windowed_numbers(pos_in_display, ordered_nums)
        items = [
            PageItem(number=None, url=None, is_current=False, is_ellipsis=True)
            if num is None
            else PageItem(
                number=num,
                url=_page_url(num, num == total_pages),
                is_current=(num == page_num),
            )
            for num in win
        ]

        slices.append(
            PageSlice(
                page_number=page_num,
                total_pages=total_pages,
                posts=chunk,
                url=url,
                output_paths=outputs,
                prev_url=newer_url,
                next_url=older_url,
                newer_url=newer_url,
                older_url=older_url,
                pages=items,
                is_index=is_idx,
            )
        )

    return slices


def select_incremental_slices(
    all_slices: list[PageSlice],
    *,
    mode: str = "stable",
    per_page: int = 10,
    is_new_newest: bool = False,
    changed_slug: Optional[str] = None,
    total_after: Optional[int] = None,
) -> list[PageSlice]:
    """
    Determine the minimal subset of PageSlices that must be rebuilt after a change.

    In `stable` mode when publishing a new post at the top:
      - Rebuilds only the index slice (2 files: index.html + posts/index.html),
      - Plus at most 1 newly frozen archive page slice when a page boundary is crossed
        (`(total_after - 1) % per_page == 0`), keeping commits <= 3 HTML files!
    """
    if not all_slices:
        return []

    norm_mode = (mode or "stable").strip().lower()
    if norm_mode != "stable":
        return all_slices

    if is_new_newest and total_after is not None:
        result = [all_slices[-1]]  # Index slice (newest)
        if len(all_slices) >= 2 and total_after > 1 and (total_after - 1) % max(1, per_page) == 0:
            result.insert(0, all_slices[-2])
        return result

    if changed_slug:
        matched = [s for s in all_slices if any(p.get("slug") == changed_slug for p in s.posts)]
        if matched:
            return matched

    return all_slices
