"""
Localization & cross-platform date formatting for note2cms.

Replaces OS-dependent strftime("%-d") and provides UI labels in English and Russian.
"""

from datetime import datetime

MONTHS = {
    "en": {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December",
    },
    "ru": {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
    },
}

TRANSLATIONS = {
    "en": {
        "min_read": "min read",
        "min_short": "min",
        "all_posts": "All posts",
        "no_posts": "No posts yet.",
        "push_hint": "Push some Markdown to get started.",
        "older_posts": "Older",
        "newer_posts": "Newer",
        "prev_page": "Previous",
        "next_page": "Next",
        "page_of": "Page {current} of {total}",
        "related_posts": "Related posts",
        "series_label": "Series",
        "series_part": "Part {order} of {total}",
        "tags_title": "Tags",
        "all_tags": "All tags",
        "posts_tagged": "Tagged: #{tag}",
        "search_title": "Search",
        "search_placeholder": "Search posts...",
        "search_no_results": "No matching posts found.",
        "previous_post": "Previous",
        "next_post": "Next",
        "photos_count": "{count} photos",
        "close": "Close",
        "rss_feed": "RSS",
        "home": "Home",
        "subtitle": "writing, published from notes.",
        "footer_powered": "Published with note2cms — the past-browser publishing protocol",
        "pinned_label": "Pinned",
        "share_post": "Share",
        "copy_link": "Copy link",
        "copied_link": "Copied ✓",
    },
    "ru": {
        "min_read": "мин чтения",
        "min_short": "мин",
        "all_posts": "Все посты",
        "no_posts": "Постов пока нет.",
        "push_hint": "Отправьте Markdown, чтобы опубликовать первый пост.",
        "older_posts": "Старее",
        "newer_posts": "Новее",
        "prev_page": "Назад",
        "next_page": "Вперёд",
        "page_of": "Страница {current} из {total}",
        "related_posts": "Похожие посты",
        "series_label": "Серия",
        "series_part": "Часть {order} из {total}",
        "tags_title": "Теги",
        "all_tags": "Все теги",
        "posts_tagged": "Тег: #{tag}",
        "search_title": "Поиск",
        "search_placeholder": "Поиск по постам...",
        "search_no_results": "Ничего не найдено.",
        "previous_post": "Предыдущий пост",
        "next_post": "Следующий пост",
        "photos_count": "Фото: {count}",
        "close": "Закрыть",
        "rss_feed": "RSS",
        "home": "Главная",
        "subtitle": "заметки, опубликованные в веб.",
        "footer_powered": "Опубликовано через note2cms",
        "pinned_label": "Закреплено",
        "share_post": "Поделиться",
        "copy_link": "Скопировать ссылку",
        "copied_link": "Скопировано ✓",
    },
}


def normalize_lang(lang: str) -> str:
    code = (lang or "en").strip().lower().split("-")[0].split("_")[0]
    return code if code in TRANSLATIONS else "en"


def format_date(date_iso: str, lang: str = "en") -> str:
    """Format an ISO date string cleanly across Windows, macOS, and Linux."""
    norm = normalize_lang(lang)
    try:
        raw = str(date_iso).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return str(date_iso)

    month_name = MONTHS[norm][dt.month]
    if norm == "ru":
        return f"{dt.day} {month_name} {dt.year}"
    return f"{month_name} {dt.day}, {dt.year}"


def get_translations(lang: str = "en") -> dict[str, str]:
    """Return UI strings for the given language code, defaulting to English."""
    norm = normalize_lang(lang)
    return dict(TRANSLATIONS[norm])
