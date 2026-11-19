"""
Unified Markdown rendering pipeline for note2cms.

Features:
- Shared extensions across local/cloud builds (fenced_code, codehilite, tables, toc, smarty, attr_list, md_in_html)
- Obsidian image embed syntax (`![[photo.jpg]]`, `![[photo.jpg|caption]]`)
- Explicit `::: gallery ... :::` blocks and automatic detection of consecutive images
- Strictly zero-JS pure-CSS scroll-snap carousel + `:target` lightbox
- Asset URL rewriting (`src`, `srcset`, `sizes`, `width`, `height`, `loading="lazy"`)
"""

import re
import shlex
import xml.etree.ElementTree as etree
from dataclasses import dataclass
from typing import Optional

import markdown
from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor
from markdown.treeprocessors import Treeprocessor

from pipeline.i18n import get_translations
from pipeline.media import ProcessedAsset, resolve_asset_match


OBSIDIAN_EMBED_RE = re.compile(r"!\[\[([^\]|]+?)(?:\|([^\]]*))?\]\]")
GALLERY_OPEN_RE = re.compile(r"^:::\s*gallery(?:\s+(.*))?$", re.IGNORECASE)
GALLERY_CLOSE_RE = re.compile(r"^:::\s*$")
SAFE_RATIO_RE = re.compile(r"^\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?$")


@dataclass
class RenderedMarkdown:
    html: str
    first_image_url: Optional[str] = None
    images: list[str] = None

    def __post_init__(self):
        if self.images is None:
            self.images = []


def _parse_gallery_attrs(attr_str: str) -> dict[str, str]:
    """Parse key=value attributes from `::: gallery caption="..." ratio=4/3`."""
    attrs: dict[str, str] = {}
    if not attr_str:
        return attrs
    try:
        tokens = shlex.split(attr_str)
    except ValueError:
        tokens = attr_str.split()
    for token in tokens:
        if "=" in token:
            k, v = token.split("=", 1)
            attrs[k.strip().lower()] = v.strip()
    return attrs


class _Note2CmsPreprocessor(Preprocessor):
    """Converts Obsidian ![[...]] embeds and `::: gallery` containers before parsing."""

    def run(self, lines: list[str]) -> list[str]:
        out: list[str] = []
        in_fence = False
        in_gallery = False
        gallery_lines: list[str] = []
        gallery_attrs: dict[str, str] = {}

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = not in_fence
                if in_gallery:
                    gallery_lines.append(line)
                else:
                    out.append(line)
                continue

            if in_fence:
                if in_gallery:
                    gallery_lines.append(line)
                else:
                    out.append(line)
                continue

            if not in_gallery:
                m_open = GALLERY_OPEN_RE.match(stripped)
                if m_open:
                    in_gallery = True
                    gallery_attrs = _parse_gallery_attrs(m_open.group(1) or "")
                    gallery_lines = []
                    continue
                out.append(self._convert_obsidian_embeds(line))
            else:
                if GALLERY_CLOSE_RE.match(stripped):
                    in_gallery = False
                    caption = gallery_attrs.get("caption", "")
                    ratio = gallery_attrs.get("ratio", "")
                    attr_parts = ['class="n2c-gallery-block"', 'markdown="1"']
                    if caption:
                        attr_parts.append(f'data-caption="{_escape_attr(caption)}"')
                    if ratio and SAFE_RATIO_RE.match(ratio):
                        attr_parts.append(f'data-ratio="{_escape_attr(ratio)}"')
                    out.append(f'<div {" ".join(attr_parts)}>')
                    out.append("")
                    for gl in gallery_lines:
                        out.append(self._convert_obsidian_embeds(gl))
                    out.append("")
                    out.append("</div>")
                    gallery_lines = []
                    gallery_attrs = {}
                else:
                    gallery_lines.append(line)

        if in_gallery:
            # Unclosed gallery block: emit lines verbatim
            for gl in gallery_lines:
                out.append(self._convert_obsidian_embeds(gl))

        return out

    @staticmethod
    def _convert_obsidian_embeds(line: str) -> str:
        def _repl(match: re.Match) -> str:
            target = match.group(1).strip()
            alt = (match.group(2) or "").strip()
            return f"![{alt}]({target})"

        return OBSIDIAN_EMBED_RE.sub(_repl, line)


def _escape_attr(val: str) -> str:
    return (
        val.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _is_image_only_paragraph(el: etree.Element) -> bool:
    """Return True if <p> contains >= 2 <img> elements and only whitespace/<br>."""
    if el.tag != "p":
        return False
    if el.text and el.text.strip():
        return False
    imgs = 0
    for child in el:
        if child.tag == "img":
            imgs += 1
        elif child.tag == "br":
            pass
        else:
            return False
        if child.tail and child.tail.strip():
            return False
    return imgs >= 2


def _collect_images(el: etree.Element) -> list[etree.Element]:
    """Recursively collect <img> elements inside an explicit gallery block."""
    found: list[etree.Element] = []
    for node in el.iter("img"):
        found.append(node)
    return found


class _MediaAndCarouselTreeprocessor(Treeprocessor):
    """Rewrites uploaded asset URLs and builds pure-CSS scroll-snap carousels."""

    def __init__(
        self,
        md,
        *,
        assets_map: Optional[dict[str, ProcessedAsset]] = None,
        enable_carousel: bool = True,
        lang: str = "en",
        collector: Optional[dict] = None,
    ):
        super().__init__(md)
        self.assets_map = assets_map or {}
        self.enable_carousel = enable_carousel
        self.i18n = get_translations(lang)
        self.collector = collector if collector is not None else {}

    def run(self, root: etree.Element) -> None:
        images_seen: list[str] = []

        # 1. Enrich every <img> element with uploaded asset metadata and lazy-loading
        for img in root.iter("img"):
            raw_src = img.get("src", "")
            matched = resolve_asset_match(raw_src, self.assets_map)
            if matched:
                img.set("src", matched.primary_url)
                img.set("width", str(matched.width))
                img.set("height", str(matched.height))
                if matched.srcset:
                    img.set("srcset", matched.srcset)
                    img.set("sizes", "(max-width: 768px) 100vw, 768px")
                images_seen.append(matched.primary_url)
            elif raw_src:
                images_seen.append(raw_src)

            img.set("loading", "lazy")
            img.set("decoding", "async")

        self.collector["images"] = images_seen
        self.collector["first_image_url"] = images_seen[0] if images_seen else None

        # 2. Build pure-CSS carousels (for explicit blocks always, and auto paragraphs when enabled)
        gallery_counter = 0
        lightboxes_to_append: list[etree.Element] = []

        # Walk parent -> child so we can replace nodes in place
        parent_map = {child: parent for parent in root.iter() for child in parent}
        candidates = list(root.iter())

        for node in candidates:
            is_explicit = (
                node.tag == "div"
                and "n2c-gallery-block" in (node.get("class") or "").split()
            )
            is_auto = self.enable_carousel and _is_image_only_paragraph(node)

            if not (is_explicit or is_auto):
                continue

            imgs = _collect_images(node)
            if not imgs:
                continue
            if is_auto and len(imgs) < 2:
                continue

            gallery_counter += 1
            caption = node.get("data-caption", "") if is_explicit else ""
            ratio = node.get("data-ratio", "") if is_explicit else ""

            carousel_el, lb_els = self._build_carousel(
                gallery_id=gallery_counter,
                imgs=imgs,
                caption=caption,
                ratio=ratio,
            )

            parent = parent_map.get(node)
            if parent is None:
                continue
            idx = list(parent).index(node)
            carousel_el.tail = node.tail
            parent.remove(node)
            parent.insert(idx, carousel_el)
            lightboxes_to_append.extend(lb_els)

        for lb in lightboxes_to_append:
            root.append(lb)

    def _build_carousel(
        self,
        gallery_id: int,
        imgs: list[etree.Element],
        caption: str = "",
        ratio: str = "",
    ) -> tuple[etree.Element, list[etree.Element]]:
        fig = etree.Element("figure")
        fig.set("class", "n2c-carousel")
        fig.set("aria-roledescription", "carousel")
        fig.set("aria-label", caption or f"Gallery {gallery_id}")
        if ratio and SAFE_RATIO_RE.match(ratio):
            fig.set("style", f"--n2c-ratio: {ratio};")

        track = etree.SubElement(fig, "div")
        track.set("class", "n2c-carousel-track")
        track.set("tabindex", "0")

        nav = etree.SubElement(fig, "nav")
        nav.set("class", "n2c-carousel-nav")
        nav.set("aria-label", "Gallery navigation")

        total = len(imgs)
        lightboxes: list[etree.Element] = []

        for idx, img in enumerate(imgs, start=1):
            slide_id = f"n2c-g{gallery_id}-s{idx}"
            lb_id = f"n2c-lb-g{gallery_id}-s{idx}"
            prev_idx = total if idx == 1 else idx - 1
            next_idx = 1 if idx == total else idx + 1
            prev_lb_id = f"n2c-lb-g{gallery_id}-s{prev_idx}"
            next_lb_id = f"n2c-lb-g{gallery_id}-s{next_idx}"

            slide = etree.SubElement(track, "figure")
            slide.set("class", "n2c-carousel-slide")
            slide.set("id", slide_id)

            trigger = etree.SubElement(slide, "a")
            trigger.set("href", f"#{lb_id}")
            trigger.set("class", "n2c-lightbox-trigger")
            alt_text = (img.get("alt") or "").strip()
            trigger.set("aria-label", alt_text or f"Image {idx}")

            # Clone img cleanly without stale tail
            img_copy = etree.Element("img")
            for attr_k, attr_v in img.attrib.items():
                img_copy.set(attr_k, attr_v)
            trigger.append(img_copy)

            if alt_text:
                slide_cap = etree.SubElement(slide, "figcaption")
                slide_cap.set("class", "n2c-slide-caption")
                slide_cap.text = alt_text

            dot = etree.SubElement(nav, "a")
            dot.set("href", f"#{slide_id}")
            dot.set("class", "n2c-carousel-dot")
            dot.set("aria-label", f"{idx} / {total}")
            dot.text = str(idx)

            # Pure-CSS :target lightbox modal
            lb = etree.Element("div")
            lb.set("id", lb_id)
            lb.set("class", "n2c-lightbox")
            lb.set("role", "dialog")
            lb.set("aria-modal", "true")
            if alt_text:
                lb.set("aria-label", alt_text)

            backdrop = etree.SubElement(lb, "a")
            backdrop.set("href", f"#{slide_id}")
            backdrop.set("class", "n2c-lightbox-backdrop")
            backdrop.set("aria-label", self.i18n["close"])

            inner = etree.SubElement(lb, "div")
            inner.set("class", "n2c-lightbox-inner")

            close_btn = etree.SubElement(inner, "a")
            close_btn.set("href", f"#{slide_id}")
            close_btn.set("class", "n2c-lightbox-close")
            close_btn.set("aria-label", self.i18n["close"])
            close_btn.text = "×"

            if total > 1:
                prev_btn = etree.SubElement(inner, "a")
                prev_btn.set("href", f"#{prev_lb_id}")
                prev_btn.set("class", "n2c-lightbox-prev")
                prev_btn.set("aria-label", self.i18n["prev_page"])
                prev_btn.text = "‹"

            lb_img = etree.SubElement(inner, "img")
            for attr_k, attr_v in img.attrib.items():
                if attr_k not in ("width", "height"):
                    lb_img.set(attr_k, attr_v)

            if total > 1:
                next_btn = etree.SubElement(inner, "a")
                next_btn.set("href", f"#{next_lb_id}")
                next_btn.set("class", "n2c-lightbox-next")
                next_btn.set("aria-label", self.i18n["next_page"])
                next_btn.text = "›"

            if alt_text:
                lb_cap = etree.SubElement(inner, "p")
                lb_cap.set("class", "n2c-lightbox-caption")
                lb_cap.text = alt_text

            lightboxes.append(lb)

        photos_label = self.i18n["photos_count"].format(count=total)
        cap_el = etree.SubElement(fig, "figcaption")
        cap_el.set("class", "n2c-carousel-caption")
        cap_el.text = f"{caption} · {photos_label}" if caption else photos_label

        return fig, lightboxes


class Note2CmsExtension(Extension):
    """Python-Markdown extension for Obsidian embeds, assets, and zero-JS carousels."""

    def __init__(self, **kwargs):
        self.config = {
            "assets_map": [{}, "Map of uploaded filename -> ProcessedAsset"],
            "enable_carousel": [True, "Automatically turn consecutive images into carousels"],
            "lang": ["en", "Site language code"],
            "collector": [{}, "Dict populated with extracted image metadata"],
        }
        super().__init__(**kwargs)

    def extendMarkdown(self, md):
        md.preprocessors.register(_Note2CmsPreprocessor(md), "n2c_preprocess", 30)
        md.treeprocessors.register(
            _MediaAndCarouselTreeprocessor(
                md,
                assets_map=self.getConfig("assets_map"),
                enable_carousel=self.getConfig("enable_carousel"),
                lang=self.getConfig("lang"),
                collector=self.getConfig("collector"),
            ),
            "n2c_media_carousel",
            15,
        )


def render_markdown(
    content: str,
    *,
    assets_map: Optional[dict[str, ProcessedAsset]] = None,
    enable_carousel: bool = True,
    lang: str = "en",
) -> RenderedMarkdown:
    """Render Markdown body into HTML and extract image metadata."""
    collector: dict = {}
    ext = Note2CmsExtension(
        assets_map=assets_map or {},
        enable_carousel=enable_carousel,
        lang=lang,
        collector=collector,
    )
    md = markdown.Markdown(
        extensions=[
            "fenced_code",
            "codehilite",
            "tables",
            "toc",
            "smarty",
            "attr_list",
            "md_in_html",
            ext,
        ],
        extension_configs={
            "codehilite": {"css_class": "highlight", "linenums": False},
            "smarty": {"smart_quotes": True},
        },
    )
    html_out = md.convert(content)
    return RenderedMarkdown(
        html=html_out,
        first_image_url=collector.get("first_image_url"),
        images=collector.get("images", []),
    )
