"""
Open Graph (1200x630) PNG card generator using Pillow.

When a post has no explicit `cover:` or inline image, generates a styled
social preview card matching the active theme's color palette.
"""

import textwrap
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# (bg, surface, text, muted, accent, rule)
THEME_PALETTES: dict[str, tuple[str, str, str, str, str, str]] = {
    "default": ("#faf9f7", "#ffffff", "#1a1a1a", "#6b6560", "#c45d3e", "#e0dcd7"),
    "swiss": ("#fafafa", "#f2f2f2", "#0a0a0a", "#444444", "#e63222", "#cccccc"),
    "brutalist": ("#ffffff", "#ffffff", "#000000", "#333333", "#000000", "#000000"),
    "brutalist2": ("#ffffff", "#ffffff", "#000000", "#333333", "#000000", "#000000"),
    "terminal": ("#0a0e14", "#0d1117", "#c0c8d8", "#5a6577", "#00ff88", "#1a2233"),
    "vaporwave": ("#1a1025", "#221533", "#e8dff5", "#8b7fa8", "#ff6ec7", "#2d1f42"),
    "ink": ("#f5f0e8", "#efe8dc", "#1a1714", "#6b5f52", "#cc3333", "#d8cebc"),
    "darkroom": ("#111111", "#1a1a1a", "#c8c0b4", "#706860", "#d4943a", "#2a2520"),
    "manuscript": ("#faf8f3", "#f0ebe0", "#1f1c18", "#6b6058", "#c44040", "#ded6c8"),
    "80s-Neon": ("#0c0b1a", "#16132e", "#f6f3ff", "#c3b6ff", "#ff4fd8", "#302a5a"),
    "abyssalobsidian": ("#0b141f", "#132235", "#e3f2ff", "#9bb2c8", "#39c6c0", "#1f2f45"),
    "AnuPpuccin": ("#11111b", "#1e1e2e", "#cdd6f4", "#a6adc8", "#cba6f7", "#45475a"),
    "arsmagna": ("#f8f1e2", "#f0e6d2", "#2f2a24", "#6e6257", "#b5452c", "#d8c7a9"),
    "autotape": ("#0f1115", "#1a1f29", "#e6e9ef", "#9aa4b2", "#5af2c0", "#2b3240"),
    "Blue Topaz": ("#f5faff", "#ffffff", "#1f2d3d", "#5b7088", "#0b84ff", "#d9e7f5"),
    "GDCT": ("#f1f7ef", "#ffffff", "#203326", "#587062", "#2c8c4b", "#d6e5da"),
    "GDCT_Dark": ("#0d1410", "#121c16", "#d9f3e2", "#9bb4a5", "#45d087", "#223126"),
    "Obsidian Nord": ("#2e3440", "#3b4252", "#eceff4", "#d8dee9", "#88c0d0", "#4c566a"),
    "Obsidian-Ayu": ("#0f1419", "#151a20", "#e6e1cf", "#b8b09b", "#f4a261", "#2a2f37"),
    "Obsidian-Charcoal": ("#121212", "#1b1b1b", "#eaeaea", "#b0b0b0", "#ff7a00", "#2b2b2b"),
    "Typewriter": ("#f3ede0", "#ebe3d2", "#292421", "#5d554f", "#8f2a1d", "#d5c8b2"),
}

_FONT_CANDIDATES_BOLD = [
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]

_FONT_CANDIDATES_REGULAR = [
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = _FONT_CANDIDATES_BOLD if bold else _FONT_CANDIDATES_REGULAR
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def generate_og_image(
    title: str,
    site_title: str,
    date_str: str = "",
    reading_time: int = 1,
    tags: Optional[list[str]] = None,
    theme: str = "default",
    min_read_label: str = "min read",
) -> bytes:
    """Render a 1200x630 PNG social card styled after `theme`."""
    bg, surface, fg, muted, accent, rule = THEME_PALETTES.get(
        theme, THEME_PALETTES["default"]
    )

    width, height = 1200, 630
    img = Image.new("RGB", (width, height), color=bg)
    draw = ImageDraw.Draw(img)

    # Outer card panel
    pad = 44
    draw.rectangle(
        [(pad, pad), (width - pad, height - pad)],
        fill=surface,
        outline=rule,
        width=3,
    )

    # Left vertical accent stripe
    draw.rectangle([(pad, pad), (pad + 14, height - pad)], fill=accent)

    font_site = _load_font(28, bold=True)
    font_title = _load_font(56, bold=True)
    font_meta = _load_font(26, bold=False)
    font_tag = _load_font(22, bold=False)

    content_x = pad + 56
    max_text_w = width - content_x - pad - 48

    # Top site header
    draw.text((content_x, pad + 42), site_title.upper(), font=font_site, fill=accent)

    # Wrapped title (up to 4 lines)
    wrapped = textwrap.wrap(title.strip() or site_title, width=28)[:4]
    title_y = pad + 125
    line_height = 70
    for line in wrapped:
        # Shrink slightly if a single token is wider than card
        draw.text((content_x, title_y), line, font=font_title, fill=fg)
        title_y += line_height

    # Tags row above footer
    tag_list = [t for t in (tags or []) if t][:4]
    if tag_list:
        tx = content_x
        ty = height - pad - 135
        for tag in tag_list:
            label = f"#{tag}"
            bbox = draw.textbbox((0, 0), label, font=font_tag)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            pill_w = tw + 26
            pill_h = th + 18
            if tx + pill_w > content_x + max_text_w:
                break
            draw.rounded_rectangle(
                [(tx, ty), (tx + pill_w, ty + pill_h)],
                radius=6,
                outline=accent,
                width=2,
            )
            draw.text((tx + 13, ty + 7), label, font=font_tag, fill=accent)
            tx += pill_w + 12

    # Divider line & footer metadata
    footer_y = height - pad - 72
    draw.line(
        [(content_x, footer_y - 18), (width - pad - 48, footer_y - 18)],
        fill=rule,
        width=2,
    )
    meta_parts = [p for p in [date_str, f"{reading_time} {min_read_label}"] if p]
    draw.text((content_x, footer_y), "  ·  ".join(meta_parts), font=font_meta, fill=muted)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
