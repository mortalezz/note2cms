"""
Media pipeline — EXIF/GPS stripping, 1 MP cap resizing, and responsive WebP generation.

Originals (capped at <= 1 MP and stripped of metadata) and responsive WebP variants
are stored directly in the static tree (`posts/assets/{slug}/...`).
"""

import base64
import hashlib
import math
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps
from slugify import slugify

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
EXT_BY_FORMAT = {
    "JPEG": "jpg",
    "PNG": "png",
    "WEBP": "webp",
    "GIF": "gif",
}


@dataclass
class ProcessedAsset:
    original_name: str
    primary_path: str  # Repo-relative path, e.g. "posts/assets/my-post/photo-a1b2c3d4.jpg"
    primary_url: str   # Public URL path, e.g. "/posts/assets/my-post/photo-a1b2c3d4.jpg"
    width: int
    height: int
    srcset: str
    files: dict[str, bytes]  # repo-relative path -> clean image bytes


def decode_base64_asset(data_str: str) -> bytes:
    """Decode a base64 string (optionally with data URI prefix) into raw bytes."""
    payload = data_str.strip()
    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1]
    return base64.b64decode(payload)


def _strip_metadata_copy(img: Image.Image) -> Image.Image:
    """Create a pixel-only copy with zero EXIF, GPS, XMP, or ICC side-channel metadata."""
    clean = Image.new(img.mode, img.size)
    clean.paste(img)
    return clean


def _save_image_bytes(img: Image.Image, fmt: str, quality: int = 85) -> bytes:
    buf = BytesIO()
    if fmt == "JPEG":
        rgb = img.convert("RGB") if img.mode not in ("RGB", "L") else img
        rgb.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    elif fmt == "PNG":
        img.save(buf, format="PNG", optimize=True)
    elif fmt == "WEBP":
        img.save(buf, format="WEBP", quality=quality, method=6)
    elif fmt == "GIF":
        img.save(buf, format="GIF")
    else:
        rgb = img.convert("RGB") if img.mode not in ("RGB", "L") else img
        rgb.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def process_image(
    raw_bytes: bytes,
    filename: str,
    slug: str,
    site_url: str = "",
    max_mp: float = 1.0,
    widths: tuple[int, ...] = (480, 960),
    max_asset_mb: float = 15.0,
) -> ProcessedAsset:
    """
    Sanitize and resize an uploaded image:
      1. Validate size and format.
      2. Auto-orient via EXIF Orientation tag.
      3. Strip all EXIF / GPS metadata.
      4. Proportionally resize if pixel count exceeds `max_mp` megapixels (default 1.0 MP).
      5. Generate clean primary asset + smaller WebP srcset variants.
    """
    if len(raw_bytes) > int(max_asset_mb * 1024 * 1024):
        raise ValueError(f"Asset '{filename}' exceeds {max_asset_mb} MB limit")

    with Image.open(BytesIO(raw_bytes)) as src:
        orig_format = (src.format or "JPEG").upper()
        if orig_format not in ALLOWED_FORMATS:
            raise ValueError(f"Unsupported image format '{orig_format}' for '{filename}'")

        oriented = ImageOps.exif_transpose(src)
        # Preserve alpha when present for PNG/WEBP, otherwise normalize to RGB
        if oriented.mode in ("RGBA", "LA") or (oriented.mode == "P" and "transparency" in oriented.info):
            target_mode = "RGBA" if orig_format in ("PNG", "WEBP") else "RGB"
            working = oriented.convert(target_mode)
            if target_mode == "RGB":
                orig_format = "JPEG"
        elif oriented.mode not in ("RGB", "L"):
            working = oriented.convert("RGB")
        else:
            working = oriented.copy()

    # Cap total pixels to max_mp megapixels (1 MP = 1,000,000 px)
    max_pixels = max(1, int(max_mp * 1_000_000))
    w, h = working.size
    if w * h > max_pixels:
        scale = math.sqrt(max_pixels / (w * h))
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        while new_w * new_h > max_pixels and (new_w > 1 or new_h > 1):
            if new_w >= new_h and new_w > 1:
                new_w -= 1
            elif new_h > 1:
                new_h -= 1
        working = working.resize((new_w, new_h), Image.Resampling.LANCZOS)

    clean_primary = _strip_metadata_copy(working)
    primary_w, primary_h = clean_primary.size

    sha8 = hashlib.sha256(raw_bytes).hexdigest()[:8]
    raw_stem = Path(filename).stem or "image"
    safe_stem = slugify(raw_stem, max_length=48) or "image"
    ext = EXT_BY_FORMAT.get(orig_format, "jpg")

    base_dir = f"posts/assets/{slug}"
    primary_path = f"{base_dir}/{safe_stem}-{sha8}.{ext}"
    prefix = site_url.rstrip("/")
    primary_url = f"{prefix}/{primary_path}"

    files: dict[str, bytes] = {
        primary_path: _save_image_bytes(clean_primary, orig_format),
    }

    srcset_entries: list[str] = []
    for target_w in sorted(set(widths)):
        if 0 < target_w < primary_w:
            target_h = max(1, round(primary_h * (target_w / primary_w)))
            resized = clean_primary.resize((target_w, target_h), Image.Resampling.LANCZOS)
            variant_path = f"{base_dir}/{safe_stem}-{sha8}-{target_w}w.webp"
            files[variant_path] = _save_image_bytes(resized, "WEBP", quality=82)
            srcset_entries.append(f"{prefix}/{variant_path} {target_w}w")

    # Include full-size WebP if primary is not already WebP, or primary itself
    if orig_format != "WEBP":
        full_webp_path = f"{base_dir}/{safe_stem}-{sha8}-{primary_w}w.webp"
        files[full_webp_path] = _save_image_bytes(clean_primary, "WEBP", quality=85)
        srcset_entries.append(f"{prefix}/{full_webp_path} {primary_w}w")
    else:
        srcset_entries.append(f"{primary_url} {primary_w}w")

    return ProcessedAsset(
        original_name=filename,
        primary_path=primary_path,
        primary_url=primary_url,
        width=primary_w,
        height=primary_h,
        srcset=", ".join(srcset_entries),
        files=files,
    )


def resolve_asset_match(src: str, assets_map: dict[str, ProcessedAsset]) -> Optional[ProcessedAsset]:
    """Match an image src from Markdown against uploaded assets by exact path or basename."""
    if not assets_map or not src:
        return None
    if src in assets_map:
        return assets_map[src]
    norm = src.lstrip("./")
    if norm in assets_map:
        return assets_map[norm]
    base = Path(src).name
    if base in assets_map:
        return assets_map[base]
    for key, asset in assets_map.items():
        if Path(key).name == base:
            return asset
    return None
