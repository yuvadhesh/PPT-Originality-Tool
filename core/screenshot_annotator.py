
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFont

from core.models import BoundingBox, DeckComparisonResult, Issue, RuleType, SlideStatus
from core.visual_diff import render_deck_to_images

logger = logging.getLogger(__name__)


def emu_to_pixel(
    emu_x: int,
    emu_y: int,
    emu_w: int,
    emu_h: int,
    slide_w_emu: int,
    slide_h_emu: int,
    img_w_px: int,
    img_h_px: int,
) -> Tuple[int, int, int, int]:
    """
    Convert shape EMU coordinates to pixel coordinates on rendered slide image:
      pixel_x = emu_x / slide_width_emu * image_width_px
      pixel_y = emu_y / slide_height_emu * image_height_px
    """
    if slide_w_emu <= 0 or slide_h_emu <= 0 or img_w_px <= 0 or img_h_px <= 0:
        return (0, 0, 0, 0)

    px_x = int(round(emu_x / slide_w_emu * img_w_px))
    px_y = int(round(emu_y / slide_h_emu * img_h_px))
    px_w = int(round(emu_w / slide_w_emu * img_w_px))
    px_h = int(round(emu_h / slide_h_emu * img_h_px))

    # Clamp dimensions
    px_w = max(1, px_w)
    px_h = max(1, px_h)
    return (px_x, px_y, px_w, px_h)


def _get_font(size: int = 14) -> ImageFont.ImageFont:
    """Load default or standard font safely across platforms."""
    font_names = ["arial.ttf", "calibri.ttf", "segoeui.ttf", "DejaVuSans.ttf"]
    for fn in font_names:
        try:
            return ImageFont.truetype(fn, size)
        except Exception:
            continue
    return ImageFont.load_default()


def apply_dimming_overlay(
    base_img: Image.Image,
    boxes_px: List[Tuple[int, int, int, int]],
    padding_px: int = 10,
    dim_percent: float = 0.30,
) -> Image.Image:
    """
    Apply a 30 percent dark overlay on the whole slide, then restore the
    original brightness inside the problem box (+ padding) so it stands out.
    """
    if not boxes_px:
        return base_img.copy()

    w, h = base_img.size
    base_rgba = base_img.convert("RGBA")

    # Alpha mask: dim_alpha everywhere, 0 inside problem boxes (+ 10px padding)
    dim_alpha = int(round(255 * dim_percent))
    alpha_mask = Image.new("L", (w, h), dim_alpha)
    mask_draw = ImageDraw.Draw(alpha_mask)

    for bx, by, bw, bh in boxes_px:
        pad_x0 = max(0, bx - padding_px)
        pad_y0 = max(0, by - padding_px)
        pad_x1 = min(w, bx + bw + padding_px)
        pad_y1 = min(h, by + bh + padding_px)
        mask_draw.rectangle([pad_x0, pad_y0, pad_x1, pad_y1], fill=0)

    black_solid = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    base_rgba.paste(black_solid, (0, 0), alpha_mask)
    return base_rgba.convert("RGB")


def draw_numbered_circle(
    draw: ImageDraw.ImageDraw,
    center_x: int,
    center_y: int,
    radius: int,
    number: int,
    fill_color: Tuple[int, int, int] = (220, 38, 38),
    font: Optional[ImageFont.ImageFont] = None,
) -> None:
    """
    Draw a numbered circle label that matches the issue number in the Issues sheet.
    """
    if font is None:
        font = _get_font(11)

    bbox = [center_x - radius, center_y - radius, center_x + radius, center_y + radius]
    draw.ellipse(bbox, fill=fill_color, outline=(255, 255, 255), width=2)

    text = f"#{number}" if number else ""
    try:
        t_box = font.getbbox(text)
        tw = t_box[2] - t_box[0]
        th = t_box[3] - t_box[1]
    except Exception:
        tw, th = 12, 10

    draw.text((center_x - tw / 2, center_y - th / 2 - 1), text, fill=(255, 255, 255), font=font)


def draw_dashed_rectangle(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],  # x0, y0, x1, y1
    color: Tuple[int, int, int] = (220, 38, 38),
    thickness: int = 4,
    dash_len: int = 10,
    gap_len: int = 6,
) -> None:
    """Draw a dashed rectangle along the given bounding box."""
    x0, y0, x1, y1 = box
    edges = [
        ((x0, y0), (x1, y0), 1, 0),   # top
        ((x1, y0), (x1, y1), 0, 1),   # right
        ((x1, y1), (x0, y1), -1, 0),  # bottom
        ((x0, y1), (x0, y0), 0, -1),  # left
    ]
    for (sx, sy), (ex, ey), dx, dy in edges:
        total_len = int(math.hypot(ex - sx, ey - sy))
        dist = 0
        while dist < total_len:
            seg_len = min(dash_len, total_len - dist)
            start_pt = (sx + dx * dist, sy + dy * dist)
            end_pt = (sx + dx * (dist + seg_len), sy + dy * (dist + seg_len))
            draw.line([start_pt, end_pt], fill=color, width=thickness)
            dist += seg_len + gap_len


def draw_padded_box_and_badge(
    draw: ImageDraw.ImageDraw,
    box_px: Tuple[int, int, int, int],  # bx, by, bw, bh
    label_num: int,
    img_size: Tuple[int, int],
    color: Tuple[int, int, int] = (220, 38, 38),
    thickness: int = 4,
    padding_px: int = 10,
    is_dashed: bool = False,
    badge_label: Optional[str] = None,
) -> None:
    """
    Draw a rectangle (4 px) with 10 px padding and a numbered circle label.
    Supports dashed border and 'Missing' text badge.
    """
    img_w, img_h = img_size
    bx, by, bw, bh = box_px
    x0 = max(0, bx - padding_px)
    y0 = max(0, by - padding_px)
    x1 = min(img_w, bx + bw + padding_px)
    y1 = min(img_h, by + bh + padding_px)

    if is_dashed:
        draw_dashed_rectangle(draw, (x0, y0, x1, y1), color=color, thickness=thickness)
    else:
        for t in range(thickness):
            draw.rectangle([x0 - t, y0 - t, x1 + t, y1 + t], outline=color)

    # Numbered circle label at corner
    radius = 12
    circle_cx = max(radius + 2, min(img_w - radius - 2, x0))
    circle_cy = max(radius + 2, min(img_h - radius - 2, y0))
    draw_numbered_circle(
        draw,
        center_x=circle_cx,
        center_y=circle_cy,
        radius=radius,
        number=label_num,
        fill_color=color,
        font=_get_font(11),
    )

    # If badge_label is set (e.g. "Missing"), draw label next to the circle
    if badge_label:
        badge_font = _get_font(12)
        try:
            bbox = badge_font.getbbox(badge_label)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except Exception:
            tw, th = 44, 12

        pad = 4
        bx0 = circle_cx + radius + 4
        by0 = circle_cy - th // 2 - pad
        bx1 = bx0 + tw + pad * 2
        by1 = by0 + th + pad * 2
        draw.rectangle([bx0, by0, bx1, by1], fill=color)
        draw.text((bx0 + pad, by0 + pad - 1), badge_label, fill=(255, 255, 255), font=badge_font)


def create_side_by_side_highlight_image(
    orig_img: Image.Image,
    rem_img: Image.Image,
    issues: List[Issue],
    slide_w_emu: int,
    slide_h_emu: int,
    max_width_px: int = 1200,
) -> Image.Image:
    """
    Highlights problem areas on original and remediated slide images:
    - Resizes each half to 600 px width (combined image 1200 px wide).
    - Applies a 30 percent dark overlay on the whole slide, then restores original
      brightness inside problem boxes (+ 10 px padding).
    - Draws red rectangle (4 px) with 10 px padding and a numbered circle label.
    - Alignment issues: green box at ORIGINAL position drawn on both images,
      red box at REMEDIATED position.
    - Missing content: red box on ORIGINAL image. On REMEDIATED image draw dashed
      red box at the same position with the label 'Missing'.
    - If there is no bounding box, does not draw a fake box; writes 'Location not
      available' under the image.
    - Header labels 'Original' and 'Remediated' readable with >= 16 px font on dark strip.
    """
    TARGET_HALF_WIDTH = 600

    # Scale each half to exactly 600 px width
    w_orig = TARGET_HALF_WIDTH
    h_orig = int(round(orig_img.height * (TARGET_HALF_WIDTH / float(orig_img.width))))
    scaled_orig = orig_img.resize((w_orig, h_orig), Image.Resampling.LANCZOS)

    w_rem = TARGET_HALF_WIDTH
    h_rem = int(round(rem_img.height * (TARGET_HALF_WIDTH / float(rem_img.width))))
    scaled_rem = rem_img.resize((w_rem, h_rem), Image.Resampling.LANCZOS)

    slide_h = max(h_orig, h_rem)
    if scaled_orig.height != slide_h:
        scaled_orig = scaled_orig.resize((w_orig, slide_h), Image.Resampling.LANCZOS)
    if scaled_rem.height != slide_h:
        scaled_rem = scaled_rem.resize((w_rem, slide_h), Image.Resampling.LANCZOS)

    COLOR_RED = (220, 38, 38)
    COLOR_GREEN = (22, 163, 74)

    orig_highlights: List[Dict] = []
    rem_highlights: List[Dict] = []
    no_loc_issues: List[int] = []

    for iss in issues:
        num = iss.issue_num or 1
        has_box = False

        # Alignment Issues: green box at ORIGINAL position on both images, red box at REMEDIATED position
        if iss.rule_type == RuleType.ALIGNMENT:
            if iss.orig_box:
                has_box = True
                orig_box_px = emu_to_pixel(
                    iss.orig_box.left_emu, iss.orig_box.top_emu,
                    iss.orig_box.width_emu, iss.orig_box.height_emu,
                    slide_w_emu, slide_h_emu, TARGET_HALF_WIDTH, slide_h
                )
                orig_highlights.append({
                    "box": orig_box_px,
                    "num": num,
                    "color": COLOR_GREEN,
                    "is_dashed": False,
                    "badge_label": None,
                })
                # Drawn on BOTH images at ORIGINAL position
                rem_highlights.append({
                    "box": orig_box_px,
                    "num": num,
                    "color": COLOR_GREEN,
                    "is_dashed": False,
                    "badge_label": None,
                })

            if iss.rem_box:
                has_box = True
                rem_box_px = emu_to_pixel(
                    iss.rem_box.left_emu, iss.rem_box.top_emu,
                    iss.rem_box.width_emu, iss.rem_box.height_emu,
                    slide_w_emu, slide_h_emu, TARGET_HALF_WIDTH, slide_h
                )
                rem_highlights.append({
                    "box": rem_box_px,
                    "num": num,
                    "color": COLOR_RED,
                    "is_dashed": False,
                    "badge_label": None,
                })

        # Missing Content: red box on ORIGINAL image; dashed red box on REMEDIATED at same pos with 'Missing'
        elif iss.rule_type == RuleType.CONTENT and ("Missing" in iss.issue_type or iss.rem_box is None):
            if iss.orig_box:
                has_box = True
                orig_box_px = emu_to_pixel(
                    iss.orig_box.left_emu, iss.orig_box.top_emu,
                    iss.orig_box.width_emu, iss.orig_box.height_emu,
                    slide_w_emu, slide_h_emu, TARGET_HALF_WIDTH, slide_h
                )
                orig_highlights.append({
                    "box": orig_box_px,
                    "num": num,
                    "color": COLOR_RED,
                    "is_dashed": False,
                    "badge_label": None,
                })
                rem_highlights.append({
                    "box": orig_box_px,
                    "num": num,
                    "color": COLOR_RED,
                    "is_dashed": True,
                    "badge_label": "Missing",
                })
            elif iss.rem_box:
                has_box = True
                rem_box_px = emu_to_pixel(
                    iss.rem_box.left_emu, iss.rem_box.top_emu,
                    iss.rem_box.width_emu, iss.rem_box.height_emu,
                    slide_w_emu, slide_h_emu, TARGET_HALF_WIDTH, slide_h
                )
                rem_highlights.append({
                    "box": rem_box_px,
                    "num": num,
                    "color": COLOR_RED,
                    "is_dashed": False,
                    "badge_label": None,
                })

        else:
            # Other issues (e.g. Font or Content with both boxes)
            if iss.orig_box:
                has_box = True
                orig_box_px = emu_to_pixel(
                    iss.orig_box.left_emu, iss.orig_box.top_emu,
                    iss.orig_box.width_emu, iss.orig_box.height_emu,
                    slide_w_emu, slide_h_emu, TARGET_HALF_WIDTH, slide_h
                )
                orig_highlights.append({
                    "box": orig_box_px,
                    "num": num,
                    "color": COLOR_RED,
                    "is_dashed": False,
                    "badge_label": None,
                })
            if iss.rem_box:
                has_box = True
                rem_box_px = emu_to_pixel(
                    iss.rem_box.left_emu, iss.rem_box.top_emu,
                    iss.rem_box.width_emu, iss.rem_box.height_emu,
                    slide_w_emu, slide_h_emu, TARGET_HALF_WIDTH, slide_h
                )
                rem_highlights.append({
                    "box": rem_box_px,
                    "num": num,
                    "color": COLOR_RED,
                    "is_dashed": False,
                    "badge_label": None,
                })

        if not has_box:
            no_loc_issues.append(num)

    # 1. Apply dimming overlay (30% dark overlay, problem boxes + 10px pad restored to full brightness)
    orig_boxes = [h["box"] for h in orig_highlights]
    rem_boxes = [h["box"] for h in rem_highlights]

    scaled_orig = apply_dimming_overlay(scaled_orig, orig_boxes, padding_px=10, dim_percent=0.30)
    scaled_rem = apply_dimming_overlay(scaled_rem, rem_boxes, padding_px=10, dim_percent=0.30)

    # 2. Draw boxes & numbered labels
    draw_orig = ImageDraw.Draw(scaled_orig)
    for h in orig_highlights:
        draw_padded_box_and_badge(
            draw=draw_orig,
            box_px=h["box"],
            label_num=h["num"],
            img_size=(TARGET_HALF_WIDTH, slide_h),
            color=h["color"],
            thickness=4,
            padding_px=10,
            is_dashed=h["is_dashed"],
            badge_label=h["badge_label"],
        )

    draw_rem = ImageDraw.Draw(scaled_rem)
    for h in rem_highlights:
        draw_padded_box_and_badge(
            draw=draw_rem,
            box_px=h["box"],
            label_num=h["num"],
            img_size=(TARGET_HALF_WIDTH, slide_h),
            color=h["color"],
            thickness=4,
            padding_px=10,
            is_dashed=h["is_dashed"],
            badge_label=h["badge_label"],
        )

    # 3. Assemble side-by-side combined image (1200 px wide)
    banner_h = 40
    header_font = _get_font(18)  # >= 16 px font
    combined_w = 1200
    footer_h = 28 if no_loc_issues else 0
    combined_h = slide_h + banner_h + footer_h

    combined = Image.new("RGB", (combined_w, combined_h), (15, 23, 42))  # Dark slate strip
    comb_draw = ImageDraw.Draw(combined)

    # Header labels: white text on dark strip
    orig_lbl = "Original"
    bbox_o = header_font.getbbox(orig_lbl)
    tw_o = bbox_o[2] - bbox_o[0]
    th_o = bbox_o[3] - bbox_o[1]
    comb_draw.text(((600 - tw_o) // 2, (banner_h - th_o) // 2 - 1), orig_lbl, fill=(255, 255, 255), font=header_font)

    rem_lbl = "Remediated"
    bbox_r = header_font.getbbox(rem_lbl)
    tw_r = bbox_r[2] - bbox_r[0]
    th_r = bbox_r[3] - bbox_r[1]
    comb_draw.text((600 + (600 - tw_r) // 2, (banner_h - th_r) // 2 - 1), rem_lbl, fill=(255, 255, 255), font=header_font)

    # Vertical divider
    comb_draw.line([(600, 0), (600, banner_h + slide_h)], fill=(51, 65, 85), width=2)

    # Paste slide halves
    combined.paste(scaled_orig, (0, banner_h))
    combined.paste(scaled_rem, (600, banner_h))

    # Footer note if any issue has no bounding box
    if no_loc_issues:
        footer_y0 = banner_h + slide_h
        comb_draw.rectangle([0, footer_y0, combined_w, combined_h], fill=(30, 41, 59))
        issues_str = ", ".join(f"#{n}" for n in no_loc_issues)
        footer_msg = f"Location not available for issue(s): {issues_str}"
        comb_draw.text((20, footer_y0 + 5), footer_msg, fill=(203, 213, 225), font=_get_font(13))

    return combined


def generate_deck_highlighted_screenshots(
    result: DeckComparisonResult,
    orig_pptx_path: str | Path,
    rem_pptx_path: str | Path,
    output_dir: str | Path,
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> Dict[int, Union[Path, str]]:
    """
    Renders presentation slides to 150 DPI PNGs once per deck,
    generates side-by-side highlighted screenshots for every failing slide,
    and returns a mapping of {slide_index: combined_image_path_or_error_string}.
    Passing slides are strictly excluded.
    If rendering fails, retries once; if still failing, writes render failure message.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    include_fonts = getattr(result, "check_fonts", False)

    # Include ONLY slides that have at least one issue (status FAIL and non-empty issues)
    failing_slides = [
        s for s in result.slide_results
        if s.status == SlideStatus.FAIL and any(
            (include_fonts or i.rule_type != RuleType.FONT) and i.is_error
            for i in s.issues
        )
    ]
    if not failing_slides:
        logger.debug("[DEBUG] No failing slides found. Skipping screenshots generation.")
        return {}

    orig_slide_map: Dict[int, Path] = {}
    rem_slide_map: Dict[int, Path] = {}
    orig_render_error: Optional[str] = None
    rem_render_error: Optional[str] = None

    # Step 1: Render Original Deck
    if progress_callback:
        progress_callback("Rendering Original presentation to PDF & PNGs (150 DPI)...", 0.15)
    try:
        orig_png_paths = render_deck_to_images(
            pptx_path=orig_pptx_path,
            expected_slide_count=result.orig_metadata.slide_count,
            dpi=150,
            prefix="original",
            retries=1,
        )
        orig_slide_map = {idx + 1: p for idx, p in enumerate(orig_png_paths)}
    except Exception as e:
        logger.error("[DEBUG] Error rendering original presentation: %s", e)
        orig_render_error = str(e)

    # Step 2: Render Remediated Deck
    if progress_callback:
        progress_callback("Rendering Remediated presentation to PDF & PNGs (150 DPI)...", 0.40)
    try:
        rem_png_paths = render_deck_to_images(
            pptx_path=rem_pptx_path,
            expected_slide_count=result.rem_metadata.slide_count,
            dpi=150,
            prefix="remediated",
            retries=1,
        )
        rem_slide_map = {idx + 1: p for idx, p in enumerate(rem_png_paths)}
    except Exception as e:
        logger.error("[DEBUG] Error rendering remediated presentation: %s", e)
        rem_render_error = str(e)

    slide_w_emu = result.orig_metadata.slide_width_emu or 9144000
    slide_h_emu = result.orig_metadata.slide_height_emu or 6858000

    annotated_map: Dict[int, Union[Path, str]] = {}
    total_failing = len(failing_slides)

    for f_idx, slide_res in enumerate(failing_slides):
        slide_num = slide_res.rem_index or slide_res.orig_index or (f_idx + 1)

        if progress_callback:
            pct = 0.50 + 0.45 * (f_idx / total_failing)
            progress_callback(
                f"Highlighting problem areas for Slide {slide_num} ({f_idx + 1}/{total_failing})...",
                pct,
            )

        # Check for render failure
        if rem_render_error or (slide_res.rem_index and slide_res.rem_index not in rem_slide_map):
            annotated_map[slide_num] = f"Render failed for the Remediated slide {slide_num}"
            continue

        if orig_render_error or (slide_res.orig_index and slide_res.orig_index not in orig_slide_map):
            annotated_map[slide_num] = f"Render failed for the Original slide {slide_num}"
            continue

        orig_img_path = orig_slide_map.get(slide_res.orig_index) if slide_res.orig_index else None
        rem_img_path = rem_slide_map.get(slide_res.rem_index) if slide_res.rem_index else None

        if not orig_img_path or not orig_img_path.exists():
            annotated_map[slide_num] = f"Render failed for the Original slide {slide_num}"
            continue

        if not rem_img_path or not rem_img_path.exists():
            annotated_map[slide_num] = f"Render failed for the Remediated slide {slide_num}"
            continue

        try:
            with Image.open(orig_img_path) as im_o, Image.open(rem_img_path) as im_r:
                orig_img = im_o.convert("RGB")
                rem_img = im_r.convert("RGB")

            relevant_issues = [
                i for i in slide_res.issues
                if (include_fonts or i.rule_type != RuleType.FONT)
            ]

            combined_img = create_side_by_side_highlight_image(
                orig_img=orig_img,
                rem_img=rem_img,
                issues=relevant_issues,
                slide_w_emu=slide_w_emu,
                slide_h_emu=slide_h_emu,
            )

            save_path = out_path / f"highlighted_slide_{slide_num:03d}.png"
            combined_img.save(str(save_path), format="PNG", optimize=True)
            annotated_map[slide_num] = save_path
        except Exception as e:
            logger.error("[DEBUG] Error generating highlighted image for Slide %d: %s", slide_num, e)
            annotated_map[slide_num] = f"Render failed for the Remediated slide {slide_num}"

    if progress_callback:
        progress_callback("Slide highlights generated successfully!", 1.0)

    return annotated_map
