from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw

from core.visual_diff import (
    compute_visual_diff,
    find_libreoffice_executable,
)


def test_find_libreoffice_executable():
    exe_path = find_libreoffice_executable()
    assert exe_path is not None
    assert Path(exe_path).exists()


def test_compute_visual_diff(tmp_path):
    # Create two test images
    img1_path = tmp_path / "img1.png"
    img2_path = tmp_path / "img2.png"
    diff_path = tmp_path / "diff.png"

    img1 = Image.new("RGB", (200, 200), color=(255, 255, 255))
    d1 = ImageDraw.Draw(img1)
    d1.rectangle([20, 20, 80, 80], fill=(0, 0, 0))
    img1.save(str(img1_path))

    # Identical image -> SSIM should be 1.0
    ssim_same, out_same = compute_visual_diff(img1_path, img1_path, diff_path)
    assert ssim_same >= 0.99
    assert out_same.exists()

    # Slightly changed image -> SSIM should decrease
    img2 = Image.new("RGB", (200, 200), color=(255, 255, 255))
    d2 = ImageDraw.Draw(img2)
    d2.rectangle([20, 20, 180, 180], fill=(0, 0, 0))
    img2.save(str(img2_path))

    ssim_diff, out_diff = compute_visual_diff(img1_path, img2_path, diff_path)
    assert ssim_diff < 0.95
    assert out_diff.exists()


def test_render_sample_decks_non_blank(tmp_path):
    """Render two sample decks and assert neither produces blank PNG images."""
    import numpy as np
    from core.visual_diff import render_deck_to_images

    orig_deck = Path("tests/sample_decks/sample_original.pptx")
    rem_deck = Path("tests/sample_decks/sample_remediated.pptx")
    assert orig_deck.exists(), f"Sample deck not found: {orig_deck}"
    assert rem_deck.exists(), f"Sample deck not found: {rem_deck}"

    orig_out = tmp_path / "orig_renders"
    rem_out = tmp_path / "rem_renders"

    orig_images = render_deck_to_images(
        pptx_path=orig_deck,
        expected_slide_count=6,
        output_dir=orig_out,
        dpi=150,
        prefix="orig",
        retries=1,
    )
    rem_images = render_deck_to_images(
        pptx_path=rem_deck,
        expected_slide_count=6,
        output_dir=rem_out,
        dpi=150,
        prefix="rem",
        retries=1,
    )

    assert len(orig_images) == 6
    assert len(rem_images) == 6

    for p in orig_images + rem_images:
        assert p.exists()
        assert p.stat().st_size > 0
        with Image.open(p) as img:
            gray = img.convert("L")
            extrema = gray.getextrema()
            # Not a solid color
            assert extrema[0] != extrema[1], f"Image {p.name} is a solid color: {extrema}"
            arr = np.array(gray)
            assert np.std(arr) > 1.0, f"Image {p.name} standard deviation too low: {np.std(arr)}"
