from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.diff_engine import (
    check_rule1_content_preservation,
    check_rule2_alignment_preservation,
    check_rule3_font_preservation,
)
from core.matcher import match_slides
from core.models import (
    DeckComparisonResult,
    Issue,
    RuleType,
    SlideData,
    SlideDiffResult,
    SlideMatch,
    SlideStatus,
)
from core.parser import parse_presentation
from core.visual_diff import (
    find_libreoffice_executable,
    generate_deck_visual_diffs,
    LibreOfficeNotFoundError,
)


def compare_presentations(
    orig_path: str | Path,
    rem_path: str | Path,
    enable_visual_preview: bool = True,
    text_threshold: float = 95.0,
    tolerance_emu: int = 45720,  # 0.05 inch default
    check_fonts: bool = False,
    progress_callback: Optional[Callable[[str, float], None]] = None,
    output_dir: Optional[str | Path] = None,
) -> DeckComparisonResult:
    """
    Compare Original vs Remediated PowerPoint presentation checking:
    - RULE 1: Content Preservation (text, images, charts, tables, notes, hyperlinks, slide count)
    - RULE 2: Alignment / Layout Preservation (EMU position, width, height, rotation, text alignment, vertical anchor, z-order)
    - RULE 3: Font Preservation (optional, if check_fonts=True)
    """
    start_time = time.time()
    orig_file = Path(orig_path)
    rem_file = Path(rem_path)

    if progress_callback:
        progress_callback("Parsing Original PowerPoint presentation...", 0.05)
    orig_meta, orig_slides = parse_presentation(
        orig_file, file_label="Original file", resolve_inherited_fonts=check_fonts
    )

    if progress_callback:
        progress_callback("Parsing Remediated PowerPoint presentation...", 0.15)
    rem_meta, rem_slides = parse_presentation(
        rem_file, file_label="Remediated file", resolve_inherited_fonts=check_fonts
    )

    deck_issues: List[Issue] = []

    # Deck-level slide count check
    if orig_meta.slide_count != rem_meta.slide_count:
        if orig_meta.slide_count > rem_meta.slide_count:
            deck_issues.append(
                Issue(
                    slide_num="Deck",
                    element_name="Slide Count",
                    rule_type=RuleType.CONTENT,
                    issue_type="Slide Count Mismatch",
                    description="Remediated presentation has fewer slides than the original.",
                    original_value=f"{orig_meta.slide_count} slides",
                    remediated_value=f"{rem_meta.slide_count} slides",
                    difference=f"-{orig_meta.slide_count - rem_meta.slide_count} slides",
                    is_error=True,
                )
            )
        else:
            deck_issues.append(
                Issue(
                    slide_num="Deck",
                    element_name="Slide Count",
                    rule_type=RuleType.CONTENT,
                    issue_type="Extra Slides Added",
                    description="Remediated presentation has additional slides.",
                    original_value=f"{orig_meta.slide_count} slides",
                    remediated_value=f"{rem_meta.slide_count} slides",
                    difference=f"+{rem_meta.slide_count - orig_meta.slide_count} slides",
                    is_error=False,
                )
            )

    if progress_callback:
        progress_callback("Matching slides...", 0.25)
    slide_matches = match_slides(orig_slides, rem_slides)

    orig_by_idx: Dict[int, SlideData] = {s.slide_index: s for s in orig_slides}
    rem_by_idx: Dict[int, SlideData] = {s.slide_index: s for s in rem_slides}

    slide_results: List[SlideDiffResult] = []
    total_matches = len(slide_matches)

    for idx, match in enumerate(slide_matches):
        if progress_callback:
            pct = 0.25 + 0.35 * (idx / max(total_matches, 1))
            progress_callback(f"Checking Rule 1 & Rule 2 on slide pair {idx + 1}/{total_matches}...", pct)

        orig_slide = orig_by_idx.get(match.orig_index) if match.orig_index else None
        rem_slide = rem_by_idx.get(match.rem_index) if match.rem_index else None
        active_slide_idx = match.rem_index if match.rem_index is not None else (match.orig_index or (idx + 1))

        # 1. RULE 1: Content Preservation
        rule1_issues = check_rule1_content_preservation(
            orig_slide,
            rem_slide,
            active_slide_idx,
            text_threshold=text_threshold,
        )

        # 2. RULE 2: Alignment / Layout Preservation
        rule2_issues = check_rule2_alignment_preservation(
            orig_slide,
            rem_slide,
            active_slide_idx,
            tolerance_emu=tolerance_emu,
        )

        # 3. RULE 3: Font Preservation (optional)
        if check_fonts:
            rule3_issues = check_rule3_font_preservation(
                orig_slide,
                rem_slide,
                active_slide_idx,
            )
        else:
            rule3_issues = []

        combined_issues = rule1_issues + rule2_issues + rule3_issues
        slide_key = f"Slide {active_slide_idx}"

        slide_res = SlideDiffResult(
            slide_key=slide_key,
            orig_index=match.orig_index,
            rem_index=match.rem_index,
            match_type=match.match_type,
            similarity_score=match.similarity_score,
            issues=combined_issues,
        )
        slide_res.update_status()
        slide_results.append(slide_res)

    # Optional side-by-side rendering (for visual viewing only, not a rule)
    if enable_visual_preview:
        visual_out_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="ppt_preview_"))
        try:
            find_libreoffice_executable()
            visual_results = generate_deck_visual_diffs(
                orig_file,
                rem_file,
                visual_out_dir,
                slide_matches,
                progress_callback=lambda msg, p: progress_callback(msg, 0.60 + 0.38 * p) if progress_callback else None,
            )

            for s_res in slide_results:
                v_key = f"rem_{s_res.rem_index}" if s_res.rem_index else f"orig_{s_res.orig_index}"
                if v_key in visual_results:
                    v_info = visual_results[v_key]
                    s_res.orig_image_path = v_info.get("orig_img")
                    s_res.rem_image_path = v_info.get("rem_img")
                    s_res.diff_image_path = v_info.get("diff_img")
        except Exception:
            # Viewing only; ignore visual render errors if LibreOffice not configured
            pass

    if progress_callback:
        progress_callback("Comparison complete!", 1.0)

    elapsed = time.time() - start_time

    deck_result = DeckComparisonResult(
        orig_filename=orig_file.name,
        rem_filename=rem_file.name,
        orig_metadata=orig_meta,
        rem_metadata=rem_meta,
        slide_matches=slide_matches,
        slide_results=slide_results,
        deck_issues=deck_issues,
        processing_time_sec=round(elapsed, 2),
        check_fonts=check_fonts,
    )

    # Assign sequential issue numbers across all issues
    for idx, iss in enumerate(deck_result.all_issues, start=1):
        iss.issue_num = idx

    return deck_result
