from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple
from rapidfuzz import fuzz

from core.diff_engine import compute_normalized_similarity, normalize_text
from core.models import SlideData, SlideMatch


def compute_slide_similarity(orig: SlideData, rem: SlideData) -> float:
    """
    Compute a composite similarity score (0.0 to 100.0) between an original and remediated slide.
    Combines title similarity, text body similarity, shape count similarity, and index proximity.
    Whitespace differences are completely ignored.
    """
    # 1. Title Similarity (0 to 100)
    norm_title_orig = normalize_text(orig.title).lower()
    norm_title_rem = normalize_text(rem.title).lower()
    if norm_title_orig and norm_title_rem:
        if norm_title_orig == norm_title_rem:
            title_score = 100.0
        else:
            lev_score = compute_normalized_similarity(norm_title_orig, norm_title_rem)
            tok_score = float(fuzz.token_sort_ratio(orig.title, rem.title))
            title_score = max(lev_score, tok_score)
    elif not norm_title_orig and not norm_title_rem:
        title_score = 70.0  # Both have no title
    else:
        title_score = 0.0

    # 2. Text Content Similarity (0 to 100)
    norm_text_orig = normalize_text(orig.text_content).lower()
    norm_text_rem = normalize_text(rem.text_content).lower()
    if norm_text_orig and norm_text_rem:
        if norm_text_orig == norm_text_rem:
            text_score = 100.0
        else:
            lev_score = compute_normalized_similarity(norm_text_orig, norm_text_rem)
            tok_score = float(fuzz.token_sort_ratio(orig.text_content, rem.text_content))
            text_score = max(lev_score, tok_score)
    elif not norm_text_orig and not norm_text_rem:
        text_score = 70.0  # Both have no text
    else:
        text_score = 10.0

    # 3. Structural Element Similarity
    # Compare images, tables, shapes count
    max_shapes = max(orig.shapes_count, rem.shapes_count, 1)
    shape_diff = abs(orig.shapes_count - rem.shapes_count)
    shape_score = max(0.0, 100.0 - (shape_diff / max_shapes) * 100.0)

    # 4. Proximity bonus (slight preference for same index or adjacent index)
    index_bonus = 0.0
    if orig.slide_index == rem.slide_index:
        index_bonus = 5.0
    elif abs(orig.slide_index - rem.slide_index) == 1:
        index_bonus = 2.0

    # Weighted calculation
    if norm_title_orig and norm_title_rem and norm_text_orig and norm_text_rem:
        composite = 0.45 * title_score + 0.45 * text_score + 0.10 * shape_score
    elif norm_title_orig and norm_title_rem:
        composite = 0.70 * title_score + 0.30 * shape_score
    elif norm_text_orig and norm_text_rem:
        composite = 0.80 * text_score + 0.20 * shape_score
    else:
        # Visual / purely shape based
        composite = shape_score

    final_score = min(100.0, composite + index_bonus)
    return round(final_score, 2)


def match_slides(
    orig_slides: List[SlideData],
    rem_slides: List[SlideData],
    min_similarity_threshold: float = 40.0,
) -> List[SlideMatch]:
    """
    Match original slides with remediated slides.
    1. If same count and high 1:1 similarity, keep 1:1 match.
    2. Otherwise, use greedy bipartite matching based on similarity matrix.
    3. Detect REORDERED, ADDED, and DELETED slides.
    """
    matches: List[SlideMatch] = []
    
    orig_count = len(orig_slides)
    rem_count = len(rem_slides)
    
    # Check if a strict 1:1 index match is suitable
    if orig_count == rem_count and orig_count > 0:
        index_matches = True
        for orig, rem in zip(orig_slides, rem_slides):
            sim = compute_slide_similarity(orig, rem)
            if sim < 50.0 and (orig.text_content or rem.text_content or orig.title or rem.title):
                index_matches = False
                break
        if index_matches:
            for orig, rem in zip(orig_slides, rem_slides):
                sim = compute_slide_similarity(orig, rem)
                matches.append(
                    SlideMatch(
                        orig_index=orig.slide_index,
                        rem_index=rem.slide_index,
                        match_type="MATCHED",
                        similarity_score=sim,
                    )
                )
            return matches

    # Build similarity score matrix: (orig_idx, rem_idx) -> score
    pair_scores: List[Tuple[float, int, int]] = []
    for orig in orig_slides:
        for rem in rem_slides:
            score = compute_slide_similarity(orig, rem)
            pair_scores.append((score, orig.slide_index, rem.slide_index))

    # Sort pairs by descending score
    pair_scores.sort(key=lambda x: x[0], reverse=True)

    matched_orig: Set[int] = set()
    matched_rem: Set[int] = set()
    orig_to_rem: Dict[int, Tuple[int, float]] = {}

    for score, o_idx, r_idx in pair_scores:
        if o_idx not in matched_orig and r_idx not in matched_rem:
            if score >= min_similarity_threshold:
                matched_orig.add(o_idx)
                matched_rem.add(r_idx)
                orig_to_rem[o_idx] = (r_idx, score)

    # Format matches ordered primarily by remediated slide order
    for rem in rem_slides:
        r_idx = rem.slide_index
        # Find which orig matched with r_idx
        found_orig = None
        found_score = 0.0
        for o_idx, (matched_r, score) in orig_to_rem.items():
            if matched_r == r_idx:
                found_orig = o_idx
                found_score = score
                break

        if found_orig is not None:
            match_type = "MATCHED" if found_orig == r_idx else "REORDERED"
            matches.append(
                SlideMatch(
                    orig_index=found_orig,
                    rem_index=r_idx,
                    match_type=match_type,
                    similarity_score=found_score,
                )
            )
        else:
            # Added slide in remediated deck
            matches.append(
                SlideMatch(
                    orig_index=None,
                    rem_index=r_idx,
                    match_type="ADDED",
                    similarity_score=0.0,
                )
            )

    # Add deleted slides from original deck
    for orig in orig_slides:
        o_idx = orig.slide_index
        if o_idx not in matched_orig:
            matches.append(
                SlideMatch(
                    orig_index=o_idx,
                    rem_index=None,
                    match_type="DELETED",
                    similarity_score=0.0,
                )
            )

    return matches
