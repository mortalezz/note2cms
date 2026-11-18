"""Tests for media pipeline (EXIF/GPS strip, 1MP cap, WebP) and zero-JS CSS carousel."""

from io import BytesIO
from PIL import Image, ExifTags

from pipeline.markdown_ext import render_markdown
from pipeline.media import process_image


def _make_jpeg_with_exif_gps(width: int = 2000, height: int = 1500) -> bytes:
    img = Image.new("RGB", (width, height), color=(120, 60, 40))
    exif = Image.Exif()
    # Orientation = 6 (90 deg CW -> transposed dims swap)
    exif[0x0112] = 6
    # Camera make
    exif[0x010F] = "TestPhone"
    # GPS IFD tag (0x8825)
    exif[0x8825] = {
        1: "N",
        2: (55.0, 45.0, 0.0),
        3: "E",
        4: (37.0, 37.0, 0.0),
    }
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes(), quality=90)
    return buf.getvalue()


def test_process_image_strips_exif_gps_and_caps_at_1mp():
    raw_bytes = _make_jpeg_with_exif_gps(2000, 1500)
    # Confirm input truly has EXIF & GPS before processing
    with Image.open(BytesIO(raw_bytes)) as src:
        assert len(src.getexif()) > 0
        assert 0x8825 in src.getexif()

    asset = process_image(raw_bytes, "IMG_001.JPG", slug="elbrus", site_url="https://blog.test")

    # Resized <= 1 MP (1,000,000 px) and EXIF orientation (6) applied (height > width)
    assert asset.width * asset.height <= 1_000_000
    assert asset.height > asset.width
    assert asset.primary_path.startswith("posts/assets/elbrus/")
    assert asset.primary_url.startswith("https://blog.test/posts/assets/elbrus/")
    assert "480w" in asset.srcset

    # Inspect every generated file: zero EXIF / GPS tags remain
    for path, content_bytes in asset.files.items():
        with Image.open(BytesIO(content_bytes)) as out_img:
            out_exif = out_img.getexif()
            assert len(out_exif) == 0, f"EXIF leaked in {path}: {dict(out_exif)}"
            assert 0x8825 not in out_exif
            assert "exif" not in out_img.info


def test_carousel_auto_explicit_and_obsidian_strictly_zero_js():
    raw1 = _make_jpeg_with_exif_gps(1600, 1200)
    raw2 = _make_jpeg_with_exif_gps(1400, 1000)
    a1 = process_image(raw1, "01.jpg", slug="trip")
    a2 = process_image(raw2, "02.jpg", slug="trip")
    assets_map = {"01.jpg": a1, "02.jpg": a2}

    md_auto = (
        "Intro text.\n\n"
        "![Dawn](01.jpg)\n"
        "![Summit](02.jpg)\n\n"
        "Outro text."
    )
    res_auto = render_markdown(md_auto, assets_map=assets_map, enable_carousel=True, lang="ru")
    assert 'class="n2c-carousel"' in res_auto.html
    assert 'class="n2c-carousel-track"' in res_auto.html
    assert 'class="n2c-lightbox"' in res_auto.html
    assert "Фото: 2" in res_auto.html
    assert a1.primary_url in res_auto.html
    assert "srcset=" in res_auto.html
    assert "<script" not in res_auto.html.lower()

    md_explicit = (
        '::: gallery caption="Elbrus 2026" ratio=4/3\n'
        "![[01.jpg|First view]]\n"
        "![[02.jpg|Second view]]\n"
        ":::"
    )
    res_exp = render_markdown(md_explicit, assets_map=assets_map, enable_carousel=True, lang="en")
    assert 'class="n2c-carousel"' in res_exp.html
    assert "--n2c-ratio: 4/3;" in res_exp.html
    assert "Elbrus 2026 · 2 photos" in res_exp.html
    assert "First view" in res_exp.html
    assert "<script" not in res_exp.html.lower()

    # Single image paragraph stays a regular <img>, not a carousel
    res_single = render_markdown("![Only one](01.jpg)", assets_map=assets_map, enable_carousel=True)
    assert 'class="n2c-carousel"' not in res_single.html
    assert "<img" in res_single.html
