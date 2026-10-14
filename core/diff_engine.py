from __future__ import annotations

import math
import re
import unicodedata
from typing import Dict, List, Optional, Set, Tuple
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from core.models import (
    BoundingBox,
    Issue,
    RuleType,
    ShapeInfo,
    SlideData,
)

# Comprehensive Symbol font to Unicode mapping
SYMBOL_TO_UNICODE: Dict[int, str] = {
    0x20: " ", 0x21: "!", 0x22: "∀", 0x23: "#", 0x24: "∃", 0x25: "%", 0x26: "&", 0x27: "∍",
    0x28: "(", 0x29: ")", 0x2A: "∗", 0x2B: "+", 0x2C: ",", 0x2D: "−", 0x2E: ".", 0x2F: "/",
    0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4", 0x35: "5", 0x36: "6", 0x37: "7",
    0x38: "8", 0x39: "9", 0x3A: ":", 0x3B: ";", 0x3C: "<", 0x3D: "=", 0x3E: ">", 0x3F: "?",
    0x40: "≅", 0x41: "Α", 0x42: "Β", 0x43: "Χ", 0x44: "Δ", 0x45: "Ε", 0x46: "Φ", 0x47: "Γ",
    0x48: "Η", 0x49: "Ι", 0x4A: "ϑ", 0x4B: "Κ", 0x4C: "Λ", 0x4D: "Μ", 0x4E: "Ν", 0x4F: "Ο",
    0x50: "Π", 0x51: "Θ", 0x52: "Ρ", 0x53: "Σ", 0x54: "Τ", 0x55: "Υ", 0x56: "ς", 0x57: "Ω",
    0x58: "Ξ", 0x59: "Ψ", 0x5A: "Ζ", 0x5B: "[", 0x5C: "∴", 0x5D: "]", 0x5E: "⊥", 0x5F: "_",
    0x60: "∼", 0x61: "α", 0x62: "β", 0x63: "χ", 0x64: "δ", 0x65: "ε", 0x66: "φ", 0x67: "γ",
    0x68: "η", 0x69: "ι", 0x6A: "ϕ", 0x6B: "κ", 0x6C: "λ", 0x6D: "μ", 0x6E: "ν", 0x6F: "ο",
    0x70: "π", 0x71: "θ", 0x72: "ρ", 0x73: "σ", 0x74: "τ", 0x75: "υ", 0x76: "ϖ", 0x77: "ω",
    0x78: "ξ", 0x79: "ψ", 0x7A: "ζ", 0x7B: "{", 0x7C: "|", 0x7D: "}", 0x7E: "∼",
    0xA0: "€", 0xA1: "ϒ", 0xA2: "′", 0xA3: "≤", 0xA4: "⁄", 0xA5: "∞", 0xA6: "ƒ", 0xA7: "♣",
    0xA8: "♦", 0xA9: "♥", 0xAA: "♠", 0xAB: "↔", 0xAC: "←", 0xAD: "↑", 0xAE: "→", 0xAF: "↓",
    0xB0: "°", 0xB1: "±", 0xB2: "″", 0xB3: "≥", 0xB4: "×", 0xB5: "∝", 0xB6: "∂", 0xB7: "•",
    0xB8: "÷", 0xB9: "≠", 0xBA: "≡", 0xBB: "≈", 0xBC: "…", 0xBD: "⏐", 0xBE: "⎯", 0xBF: "↵",
    0xC0: "ℵ", 0xC1: "ℑ", 0xC2: "ℜ", 0xC3: "℘", 0xC4: "⊗", 0xC5: "⊕", 0xC6: "∅", 0xC7: "∩",
    0xC8: "∪", 0xC9: "⊃", 0xCA: "⊇", 0xCB: "⊄", 0xCC: "⊂", 0xCD: "⊆", 0xCE: "∈", 0xCF: "∉",
    0xD0: "∠", 0xD1: "∇", 0xD2: "®", 0xD3: "©", 0xD4: "™", 0xD5: "∏", 0xD6: "√", 0xD7: "⋅",
    0xD8: "¬", 0xD9: "∧", 0xDA: "∨", 0xDB: "⇔", 0xDC: "⇐", 0xDD: "⇑", 0xDE: "⇒", 0xDF: "⇓",
    0xE0: "◊", 0xE1: "〈", 0xE2: "®", 0xE3: "©", 0xE4: "™", 0xE5: "∑", 0xE6: "⎛", 0xE7: "⎜",
    0xE8: "⎝", 0xE9: "⎡", 0xEA: "⎢", 0xEB: "⎣", 0xEC: "⎧", 0xED: "⎨", 0xEE: "⎩", 0xEF: "⎪",
    0xF1: "〉", 0xF2: "∫", 0xF3: "⌠", 0xF4: "⎮", 0xF5: "⌡", 0xF6: "⎞", 0xF7: "⎟", 0xF8: "⎠",
    0xF9: "⎤", 0xFA: "⎥", 0xFB: "⎦", 0xFC: "⎫", 0xFD: "⎬", 0xFE: "⎭",
}


def map_symbol_font_text(text: Optional[str], font_name: Optional[str] = None) -> str:
    """
    If font_name is Symbol, Wingdings, or a symbol typeface, map characters to Unicode.
    Also maps Unicode Private Use Area (PUA) characters in the range 0xF020 to 0xF0FF,
    which Microsoft Office uses when storing Symbol font text.
    """
    if not text:
        return ""
    fn_lower = (font_name or "").lower()
    is_symbol = any(s in fn_lower for s in ("symbol", "wingding", "webdings", "mt extra"))
    chars = []
    for c in str(text):
        code = ord(c)
        if 0xF000 <= code <= 0xF0FF:
            offset = code - 0xF000
            chars.append(SYMBOL_TO_UNICODE.get(offset, chr(offset) if 32 <= offset <= 126 else c))
        elif is_symbol and code in SYMBOL_TO_UNICODE:
            chars.append(SYMBOL_TO_UNICODE[code])
        else:
            chars.append(c)
    return "".join(chars)


def normalize_text(text: Optional[str]) -> str:
    """
    Normalization for text comparison (Rule 1: Content):
    - Maps PUA symbol codes (0xF020-0xF0FF) to Unicode.
    - Mathematical Alphanumeric Symbols (U+1D400-U+1D7FF) normalized via NFKC.
    - Strips combining diacritical marks (overbars, hats, tildes, etc.).
    - Unicode minus (U+2212), en dash (U+2013), em dash (U+2014), and other dash variants are equal to '-'.
    - Delta normalization: 'D' from symbol font / preceding math Greek characters treated as 'Δ'.
    - Replaces any run of whitespace/NBSP with a single space and trims.
    """
    if not text:
        return ""
    s = map_symbol_font_text(str(text))
    s = unicodedata.normalize("NFKC", s)
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"[\u2212\u2010\u2011\u2012\u2013\u2014\u2015\ufe63\uff0d]", "-", s)
    s = re.sub(r"\bDq\b", "Δθ", s)
    s = re.sub(r"\bDθ\b", "Δθ", s)
    s = re.sub(r"[\s\u00a0\u2000-\u200b\u202f\ufeff]+", " ", s).strip()
    return s


# Alias for backwards compatibility
_normalize_text = normalize_text


def compute_normalized_similarity(norm_orig: str, norm_rem: str) -> float:
    """
    Compute similarity (0.0 to 100.0) between normalized strings.
    If identical, returns 100.0.
    For short strings (under 30 characters), incorporates rapidfuzz partial_ratio
    when the original short string is found inside a longer remediated string.
    """
    if not norm_orig and not norm_rem:
        return 100.0
    if norm_orig == norm_rem:
        return 100.0
    if not norm_orig or not norm_rem:
        return 0.0

    dist = Levenshtein.distance(norm_orig, norm_rem)
    max_len = max(len(norm_orig), len(norm_rem))
    sim = max(0.0, 100.0 * (1.0 - dist / max_len)) if max_len > 0 else 0.0

    orig_ns = re.sub(r"[\s\u00a0]+", "", norm_orig)
    rem_ns = re.sub(r"[\s\u00a0]+", "", norm_rem)
    if orig_ns and rem_ns:
        if orig_ns in rem_ns:
            return 100.0

    # Partial matching for short strings (under 30 chars) found inside longer strings
    if len(norm_orig) < 30 and len(norm_rem) >= len(norm_orig):
        p_ratio = float(fuzz.partial_ratio(norm_orig, norm_rem))
        p_ratio_ns = float(fuzz.partial_ratio(orig_ns, rem_ns)) if orig_ns and rem_ns else 0.0
        best_p = max(p_ratio, p_ratio_ns)
        if best_p >= 85.0:
            sim = max(sim, best_p)

    return round(sim, 2)



def check_rule1_content_preservation(
    orig: Optional[SlideData],
    rem: Optional[SlideData],
    slide_index: int,
    text_threshold: float = 95.0,
) -> List[Issue]:
    """
    RULE 1: Content Preservation
    Every piece of content in the ORIGINAL must exist in the REMEDIATED file.
    - All text (shapes, text boxes, placeholders, grouped shapes, table cells)
    - All images, charts, tables, shapes (by type, count, and image hash)
    - Table structure (rows/columns)
    - Speaker notes text
    - Hyperlinks (text and URL)
    Missing content = Error. Extra content in remediated = Info.
    """
    issues: List[Issue] = []

    # 1. Slide Existence
    if rem is None:
        issues.append(
            Issue(
                slide_num=slide_index,
                element_name=f"Original Slide {orig.slide_index if orig else slide_index}",
                rule_type=RuleType.CONTENT,
                issue_type="Missing Slide",
                description=f"Slide from original presentation is missing in remediated file.",
                original_value=f"Slide {orig.slide_index if orig else slide_index} ('{orig.title if orig else ''}')",
                remediated_value="(Deleted)",
                difference="Missing",
                is_error=True,
            )
        )
        return issues

    if orig is None:
        issues.append(
            Issue(
                slide_num=slide_index,
                element_name=f"Remediated Slide {rem.slide_index}",
                rule_type=RuleType.CONTENT,
                issue_type="Extra Slide",
                description=f"Extra slide present in remediated file that did not exist in original.",
                original_value="None",
                remediated_value=f"Slide {rem.slide_index} ('{rem.title}')",
                difference="Added",
                is_error=False,
            )
        )
        return issues

    # 2. Text Content Check
    rem_combined_text = normalize_text(rem.text_content or " ".join(s.text for s in rem.shapes if s.text))
    rem_normalized_blocks = [normalize_text(b) for b in rem.text_blocks if normalize_text(b)]

    rem_shapes_with_text: List[Tuple[ShapeInfo, str]] = []
    for s in rem.shapes:
        s_norm = normalize_text(s.text)
        if s_norm:
            rem_shapes_with_text.append((s, s_norm))

    rem_by_id = {s.shape_id: s for s in rem.shapes}
    rem_by_name = {s.name: s for s in rem.shapes}

    group_reported_issues: Dict[int, Issue] = {}
    checked_strings: Set[str] = set()

    for orig_shape in orig.shapes:
        raw_orig_text = orig_shape.text or ""
        norm_orig = normalize_text(raw_orig_text)
        if not norm_orig:
            continue

        # Rule 3: Do not report text with fewer than 3 meaningful characters
        meaningful_chars = re.findall(r"[A-Za-z0-9]", norm_orig)
        if len(meaningful_chars) < 3:
            continue

        checked_strings.add(norm_orig)

        # Check whether original text appears as a substring of whole remediated slide text
        norm_orig_ns = re.sub(r"[\s\u00a0]+", "", norm_orig)
        rem_combined_ns = re.sub(r"[\s\u00a0]+", "", rem_combined_text)
        if norm_orig in rem_combined_text or (norm_orig_ns and norm_orig_ns in rem_combined_ns):
            continue

        if len(norm_orig) < 30 and len(rem_combined_text) >= len(norm_orig) and (
            fuzz.partial_ratio(norm_orig, rem_combined_text) >= text_threshold
            or (norm_orig_ns and len(rem_combined_ns) >= len(norm_orig_ns) and fuzz.partial_ratio(norm_orig_ns, rem_combined_ns) >= text_threshold)
        ):
            continue

        # 1. First try to match by shape id/name and similar position
        cand_shape: Optional[ShapeInfo] = None
        if orig_shape.shape_id in rem_by_id and rem_by_id[orig_shape.shape_id].text:
            cand_shape = rem_by_id[orig_shape.shape_id]
        elif orig_shape.name in rem_by_name and rem_by_name[orig_shape.name].text:
            cand_shape = rem_by_name[orig_shape.name]
        else:
            o_cx = orig_shape.left_emu + orig_shape.width_emu // 2
            o_cy = orig_shape.top_emu + orig_shape.height_emu // 2
            for s, s_norm in rem_shapes_with_text:
                r_cx = s.left_emu + s.width_emu // 2
                r_cy = s.top_emu + s.height_emu // 2
                dist_emu = math.hypot(o_cx - r_cx, o_cy - r_cy)
                if dist_emu <= 457200:  # ~0.5 inch
                    cand_shape = s
                    break

        matched = False
        if cand_shape and cand_shape.text:
            cand_norm = normalize_text(cand_shape.text)
            sim = compute_normalized_similarity(norm_orig, cand_norm)
            if sim >= text_threshold:
                matched = True

        if matched:
            continue

        # 2. If similarity is below threshold, search ALL remediated shapes on the same slide
        best_score = 0.0
        best_rem_shape: Optional[ShapeInfo] = None
        best_match_text = ""

        for r_shape, r_norm in rem_shapes_with_text:
            score = compute_normalized_similarity(norm_orig, r_norm)
            if score > best_score:
                best_score = score
                best_rem_shape = r_shape
                best_match_text = r_norm

        for rb in rem_normalized_blocks:
            score = compute_normalized_similarity(norm_orig, rb)
            if score > best_score:
                best_score = score
                best_match_text = rb

        if best_score >= text_threshold:
            continue

        # 3. Substring / partial check in combined text again
        if (
            norm_orig in rem_combined_text
            or (norm_orig_ns and norm_orig_ns in rem_combined_ns)
            or (
                len(norm_orig) < 30
                and len(rem_combined_text) >= len(norm_orig)
                and (
                    fuzz.partial_ratio(norm_orig, rem_combined_text) >= text_threshold
                    or (norm_orig_ns and len(rem_combined_ns) >= len(norm_orig_ns) and fuzz.partial_ratio(norm_orig_ns, rem_combined_ns) >= text_threshold)
                )
            )
        ):
            continue

        # Group shape deduplication
        parent_gid = orig_shape.parent_group_id
        if parent_gid is not None and parent_gid in group_reported_issues:
            existing_iss = group_reported_issues[parent_gid]
            existing_iss.original_value += f" | {norm_orig}"
            continue

        orig_box = BoundingBox(orig_shape.left_emu, orig_shape.top_emu, orig_shape.width_emu, orig_shape.height_emu)
        rem_box = BoundingBox(best_rem_shape.left_emu, best_rem_shape.top_emu, best_rem_shape.width_emu, best_rem_shape.height_emu) if best_rem_shape else None

        rem_display_val = f"[{best_rem_shape.name}] {best_match_text}" if best_rem_shape else (best_match_text if best_match_text else "(Not found)")

        iss = Issue(
            slide_num=slide_index,
            element_name=orig_shape.name or "Slide Text",
            rule_type=RuleType.CONTENT,
            issue_type="Missing Text",
            description=f"Text from original shape '{orig_shape.name or 'Slide Text'}' was not found in remediated slide.",
            original_value=norm_orig,
            remediated_value=rem_display_val,
            difference=f"Similarity: {best_score:.1f}% (Threshold: {text_threshold}%)",
            is_error=True,
            orig_box=orig_box,
            rem_box=rem_box,
        )
        issues.append(iss)
        if parent_gid is not None:
            group_reported_issues[parent_gid] = iss

    # Check any text blocks not covered by shapes (e.g., tables or standalone blocks)
    for orig_block in orig.text_blocks:
        norm_orig = normalize_text(orig_block)
        if not norm_orig or norm_orig in checked_strings:
            continue

        meaningful_chars = re.findall(r"[A-Za-z0-9]", norm_orig)
        if len(meaningful_chars) < 3:
            continue

        if norm_orig in rem_combined_text or any(norm_orig in rb for rb in rem_normalized_blocks):
            continue

        if len(norm_orig) < 30 and len(rem_combined_text) >= len(norm_orig) and fuzz.partial_ratio(norm_orig, rem_combined_text) >= text_threshold:
            continue

        best_score = 0.0
        best_rem_shape = None
        best_match_text = ""
        for r_shape, r_norm in rem_shapes_with_text:
            score = compute_normalized_similarity(norm_orig, r_norm)
            if score > best_score:
                best_score = score
                best_rem_shape = r_shape
                best_match_text = r_norm

        for rb in rem_normalized_blocks:
            score = compute_normalized_similarity(norm_orig, rb)
            if score > best_score:
                best_score = score
                best_match_text = rb

        if best_score < text_threshold:
            rem_display_val = f"[{best_rem_shape.name}] {best_match_text}" if best_rem_shape else (best_match_text if best_match_text else "(Not found)")
            issues.append(
                Issue(
                    slide_num=slide_index,
                    element_name="Slide Text",
                    rule_type=RuleType.CONTENT,
                    issue_type="Missing Text",
                    description="Text from original slide is missing or altered in remediated slide.",
                    original_value=norm_orig,
                    remediated_value=rem_display_val,
                    difference=f"Similarity: {best_score:.1f}% (Threshold: {text_threshold}%)",
                    is_error=True,
                )
            )

    # 3. Image Preservation (by hash and count/size)
    rem_image_hashes = {s.image_hash for s in rem.shapes if s.is_image and s.image_hash}
    for orig_img in orig.shapes:
        if orig_img.is_image:
            if orig_img.image_hash and orig_img.image_hash in rem_image_hashes:
                continue
            # If a shape contains an image of an equation, compare by image hash and size/position, not by text
            matched_by_size = False
            for r_s in rem.shapes:
                if r_s.is_image or "equation" in r_s.name.lower() or "object" in r_s.name.lower():
                    if orig_img.width_emu > 0 and orig_img.height_emu > 0 and r_s.width_emu > 0 and r_s.height_emu > 0:
                        w_ratio = min(orig_img.width_emu, r_s.width_emu) / max(orig_img.width_emu, r_s.width_emu)
                        h_ratio = min(orig_img.height_emu, r_s.height_emu) / max(orig_img.height_emu, r_s.height_emu)
                        o_cx = orig_img.left_emu + orig_img.width_emu // 2
                        o_cy = orig_img.top_emu + orig_img.height_emu // 2
                        r_cx = r_s.left_emu + r_s.width_emu // 2
                        r_cy = r_s.top_emu + r_s.height_emu // 2
                        dist = math.hypot(o_cx - r_cx, o_cy - r_cy)
                        if w_ratio >= 0.6 and h_ratio >= 0.6 and dist <= 914400:
                            matched_by_size = True
                            break
            if matched_by_size:
                continue

            issues.append(
                Issue(
                    slide_num=slide_index,
                    element_name=orig_img.name,
                    rule_type=RuleType.CONTENT,
                    issue_type="Missing Image",
                    description=f"Image '{orig_img.name}' from original slide is missing in remediated slide.",
                    original_value=f"Image (Hash: {orig_img.image_hash[:8] if orig_img.image_hash else 'N/A'})",
                    remediated_value="Missing",
                    difference="Not found in remediated slide",
                    is_error=True,
                    orig_box=BoundingBox(orig_img.left_emu, orig_img.top_emu, orig_img.width_emu, orig_img.height_emu),
                )
            )

    if orig.images_count > rem.images_count:
        missing_count = orig.images_count - rem.images_count
        # If not already flagged by hash
        if not any(i.issue_type == "Missing Image" for i in issues):
            o_img_shape = next((s for s in orig.shapes if s.is_image), None)
            o_box = BoundingBox(o_img_shape.left_emu, o_img_shape.top_emu, o_img_shape.width_emu, o_img_shape.height_emu) if o_img_shape else None
            issues.append(
                Issue(
                    slide_num=slide_index,
                    element_name="Images",
                    rule_type=RuleType.CONTENT,
                    issue_type="Missing Image",
                    description=f"{missing_count} image(s) missing in remediated slide.",
                    original_value=f"{orig.images_count} image(s)",
                    remediated_value=f"{rem.images_count} image(s)",
                    difference=f"-{missing_count} image(s)",
                    is_error=True,
                    orig_box=o_box,
                )
            )
    elif rem.images_count > orig.images_count:
        r_img_shape = next((s for s in rem.shapes if s.is_image), None)
        r_box = BoundingBox(r_img_shape.left_emu, r_img_shape.top_emu, r_img_shape.width_emu, r_img_shape.height_emu) if r_img_shape else None
        issues.append(
            Issue(
                slide_num=slide_index,
                element_name="Images",
                rule_type=RuleType.CONTENT,
                issue_type="Extra Image",
                description=f"{rem.images_count - orig.images_count} extra image(s) found in remediated slide.",
                original_value=f"{orig.images_count} image(s)",
                remediated_value=f"{rem.images_count} image(s)",
                difference=f"+{rem.images_count - orig.images_count} image(s)",
                is_error=False,
                rem_box=r_box,
            )
        )

    # 4. Chart Preservation
    if orig.charts_count > rem.charts_count:
        diff_c = orig.charts_count - rem.charts_count
        o_chart = next((s for s in orig.shapes if s.is_chart), None)
        o_box = BoundingBox(o_chart.left_emu, o_chart.top_emu, o_chart.width_emu, o_chart.height_emu) if o_chart else None
        issues.append(
            Issue(
                slide_num=slide_index,
                element_name="Charts",
                rule_type=RuleType.CONTENT,
                issue_type="Missing Chart",
                description=f"{diff_c} chart(s) missing in remediated slide.",
                original_value=f"{orig.charts_count} chart(s)",
                remediated_value=f"{rem.charts_count} chart(s)",
                difference=f"-{diff_c} chart(s)",
                is_error=True,
                orig_box=o_box,
            )
        )
    elif rem.charts_count > orig.charts_count:
        r_chart = next((s for s in rem.shapes if s.is_chart), None)
        r_box = BoundingBox(r_chart.left_emu, r_chart.top_emu, r_chart.width_emu, r_chart.height_emu) if r_chart else None
        issues.append(
            Issue(
                slide_num=slide_index,
                element_name="Charts",
                rule_type=RuleType.CONTENT,
                issue_type="Extra Chart",
                description="Extra chart added in remediated slide.",
                original_value=f"{orig.charts_count} chart(s)",
                remediated_value=f"{rem.charts_count} chart(s)",
                difference=f"+{rem.charts_count - orig.charts_count} chart(s)",
                is_error=False,
                rem_box=r_box,
            )
        )

    # 5. Table Preservation & Structure
    if orig.tables_count > rem.tables_count:
        diff_t = orig.tables_count - rem.tables_count
        o_tbl = next((s for s in orig.shapes if s.is_table), None)
        o_box = BoundingBox(o_tbl.left_emu, o_tbl.top_emu, o_tbl.width_emu, o_tbl.height_emu) if o_tbl else None
        issues.append(
            Issue(
                slide_num=slide_index,
                element_name="Tables",
                rule_type=RuleType.CONTENT,
                issue_type="Missing Table",
                description=f"{diff_t} table(s) missing in remediated slide.",
                original_value=f"{orig.tables_count} table(s)",
                remediated_value=f"{rem.tables_count} table(s)",
                difference=f"-{diff_t} table(s)",
                is_error=True,
                orig_box=o_box,
            )
        )
    elif rem.tables_count > orig.tables_count:
        r_tbl = next((s for s in rem.shapes if s.is_table), None)
        r_box = BoundingBox(r_tbl.left_emu, r_tbl.top_emu, r_tbl.width_emu, r_tbl.height_emu) if r_tbl else None
        issues.append(
            Issue(
                slide_num=slide_index,
                element_name="Tables",
                rule_type=RuleType.CONTENT,
                issue_type="Extra Table",
                description="Extra table added in remediated slide.",
                original_value=f"{orig.tables_count} table(s)",
                remediated_value=f"{rem.tables_count} table(s)",
                difference=f"+{rem.tables_count - orig.tables_count} table(s)",
                is_error=False,
                rem_box=r_box,
            )
        )

    # Compare matched table rows and columns
    for t_idx, (t_orig, t_rem) in enumerate(zip(orig.tables, rem.tables), start=1):
        t_name = t_rem.name or f"Table {t_idx}"
        o_tbl = next((s for s in orig.shapes if s.is_table and (s.name == t_name or s.shape_id == t_orig.shape_id)), None)
        r_tbl = next((s for s in rem.shapes if s.is_table and (s.name == t_name or s.shape_id == t_rem.shape_id)), None)
        t_obox = BoundingBox(o_tbl.left_emu, o_tbl.top_emu, o_tbl.width_emu, o_tbl.height_emu) if o_tbl else None
        t_rbox = BoundingBox(r_tbl.left_emu, r_tbl.top_emu, r_tbl.width_emu, r_tbl.height_emu) if r_tbl else None

        if t_orig.rows != t_rem.rows:
            issues.append(
                Issue(
                    slide_num=slide_index,
                    element_name=t_name,
                    rule_type=RuleType.CONTENT,
                    issue_type="Table Rows Mismatch",
                    description=f"Table '{t_name}' row count does not match original.",
                    original_value=f"{t_orig.rows} rows",
                    remediated_value=f"{t_rem.rows} rows",
                    difference=f"{t_rem.rows - t_orig.rows:+d} rows",
                    is_error=True,
                    orig_box=t_obox,
                    rem_box=t_rbox,
                )
            )
        if t_orig.cols != t_rem.cols:
            issues.append(
                Issue(
                    slide_num=slide_index,
                    element_name=t_name,
                    rule_type=RuleType.CONTENT,
                    issue_type="Table Columns Mismatch",
                    description=f"Table '{t_name}' column count does not match original.",
                    original_value=f"{t_orig.cols} columns",
                    remediated_value=f"{t_rem.cols} columns",
                    difference=f"{t_rem.cols - t_orig.cols:+d} columns",
                    is_error=True,
                    orig_box=t_obox,
                    rem_box=t_rbox,
                )
            )

    # 6. Speaker Notes Preservation
    orig_notes_clean = normalize_text(orig.notes)
    rem_notes_clean = normalize_text(rem.notes)

    if orig_notes_clean and not rem_notes_clean:
        issues.append(
            Issue(
                slide_num=slide_index,
                element_name="Speaker Notes",
                rule_type=RuleType.CONTENT,
                issue_type="Missing Speaker Notes",
                description="Speaker notes present in original slide were deleted in remediated slide.",
                original_value=orig.notes.strip(),
                remediated_value="Empty",
                difference="Deleted",
                is_error=True,
            )
        )
    elif orig_notes_clean and rem_notes_clean:
        if orig_notes_clean == rem_notes_clean:
            pass  # Whitespace-only differences produce ZERO issues
        else:
            notes_sim = compute_normalized_similarity(orig_notes_clean, rem_notes_clean)
            if notes_sim < text_threshold:
                issues.append(
                    Issue(
                        slide_num=slide_index,
                        element_name="Speaker Notes",
                        rule_type=RuleType.CONTENT,
                        issue_type="Changed Speaker Notes",
                        description="Speaker notes text differs from original.",
                        original_value=orig.notes.strip(),
                        remediated_value=rem.notes.strip(),
                        difference=f"Similarity: {notes_sim:.1f}% (Threshold: {text_threshold}%)",
                        is_error=True,
                    )
                )
    elif rem_notes_clean and not orig_notes_clean:
        issues.append(
            Issue(
                slide_num=slide_index,
                element_name="Speaker Notes",
                rule_type=RuleType.CONTENT,
                issue_type="Extra Speaker Notes",
                description="Speaker notes added in remediated slide.",
                original_value="Empty",
                remediated_value=rem.notes.strip(),
                difference="Added",
                is_error=False,
            )
        )

    # 7. Hyperlinks Preservation (Text & URL)
    # Hyperlink URLs only have leading/trailing whitespace trimmed
    orig_links = {h.url.strip(): h.text for h in orig.hyperlinks if h.url and h.url.strip()}
    rem_links = {h.url.strip(): h.text for h in rem.hyperlinks if h.url and h.url.strip()}

    for url, link_text in orig_links.items():
        if url not in rem_links:
            issues.append(
                Issue(
                    slide_num=slide_index,
                    element_name="Hyperlink",
                    rule_type=RuleType.CONTENT,
                    issue_type="Missing Hyperlink",
                    description=f"Hyperlink destination '{url}' is missing in remediated slide.",
                    original_value=f"{url} ('{link_text}')",
                    remediated_value="Missing",
                    difference="Not found",
                    is_error=True,
                )
            )
        else:
            # Check link text with light whitespace normalization
            rem_text = rem_links[url]
            if normalize_text(link_text) != normalize_text(rem_text):
                issues.append(
                    Issue(
                        slide_num=slide_index,
                        element_name="Hyperlink Text",
                        rule_type=RuleType.CONTENT,
                        issue_type="Changed Hyperlink Text",
                        description=f"Visible hyperlink text for URL '{url}' was modified.",
                        original_value=link_text,
                        remediated_value=rem_text,
                        difference=f"'{link_text}' -> '{rem_text}'",
                        is_error=True,
                    )
                )

    for url, link_text in rem_links.items():
        if url not in orig_links:
            issues.append(
                Issue(
                    slide_num=slide_index,
                    element_name="Hyperlink",
                    rule_type=RuleType.CONTENT,
                    issue_type="Extra Hyperlink",
                    description=f"New hyperlink added in remediated slide.",
                    original_value="None",
                    remediated_value=f"{url} ('{link_text}')",
                    difference="Added",
                    is_error=False,
                )
            )

    return issues


def _match_shapes_between_slides(
    orig_shapes: List[ShapeInfo],
    rem_shapes: List[ShapeInfo],
) -> List[Tuple[ShapeInfo, ShapeInfo]]:
    """
    Match each shape in remediated to the corresponding original shape:
    1. By shape id/name first.
    2. By shape type + text similarity + nearest position.
    """
    matched_pairs: List[Tuple[ShapeInfo, ShapeInfo]] = []
    matched_orig: Set[int] = set()
    matched_rem: Set[int] = set()

    # Pass 1A: Match by exact shape_id first (if shape_id > 0)
    for r_idx, rem_s in enumerate(rem_shapes):
        if r_idx in matched_rem:
            continue
        if rem_s.shape_id and rem_s.shape_id > 0:
            for o_idx, orig_s in enumerate(orig_shapes):
                if o_idx in matched_orig:
                    continue
                if orig_s.shape_id == rem_s.shape_id and (rem_s.shape_type == orig_s.shape_type or rem_s.is_image == orig_s.is_image):
                    matched_pairs.append((orig_s, rem_s))
                    matched_orig.add(o_idx)
                    matched_rem.add(r_idx)
                    break

    # Pass 1B: Match by exact name + shape_type, disambiguating duplicates by text similarity & position proximity
    for r_idx, rem_s in enumerate(rem_shapes):
        if r_idx in matched_rem:
            continue
        best_o_idx = None
        best_score = -1e9
        for o_idx, orig_s in enumerate(orig_shapes):
            if o_idx in matched_orig:
                continue
            if rem_s.name == orig_s.name and (rem_s.shape_type == orig_s.shape_type or rem_s.is_image == orig_s.is_image):
                norm_o = normalize_text(orig_s.text)
                norm_r = normalize_text(rem_s.text)
                if norm_o or norm_r:
                    text_sim = 100.0 if norm_o == norm_r else compute_normalized_similarity(norm_o, norm_r)
                else:
                    text_sim = 100.0
                dist_emu = math.hypot(rem_s.left_emu - orig_s.left_emu, rem_s.top_emu - orig_s.top_emu)
                score = text_sim * 10.0 - (dist_emu / 91440.0)  # prioritize text, then closer position
                if score > best_score:
                    best_score = score
                    best_o_idx = o_idx
        if best_o_idx is not None:
            matched_pairs.append((orig_shapes[best_o_idx], rem_s))
            matched_orig.add(best_o_idx)
            matched_rem.add(r_idx)

    # Pass 2: Bipartite matching for remaining shapes by type + text + position
    unmatched_pairs: List[Tuple[float, int, int]] = []
    for o_idx, orig_s in enumerate(orig_shapes):
        if o_idx in matched_orig:
            continue
        for r_idx, rem_s in enumerate(rem_shapes):
            if r_idx in matched_rem:
                continue

            score = 0.0
            # Same type bonus
            if orig_s.shape_type == rem_s.shape_type:
                score += 40.0
            elif (orig_s.is_image and rem_s.is_image) or (orig_s.is_table and rem_s.is_table):
                score += 40.0

            # Text similarity on normalized text
            norm_o = normalize_text(orig_s.text)
            norm_r = normalize_text(rem_s.text)
            if norm_o and norm_r:
                sim = 100.0 if norm_o == norm_r else compute_normalized_similarity(norm_o, norm_r)
                score += 0.35 * sim
            elif not norm_o and not norm_r:
                score += 0.35 * 100.0

            # Position proximity (in EMU)
            dist_emu = math.hypot(rem_s.left_emu - orig_s.left_emu, rem_s.top_emu - orig_s.top_emu)
            dist_inches = dist_emu / 914400.0
            score += max(0.0, 25.0 - dist_inches * 5.0)

            unmatched_pairs.append((score, o_idx, r_idx))

    unmatched_pairs.sort(key=lambda x: x[0], reverse=True)
    for score, o_idx, r_idx in unmatched_pairs:
        if o_idx not in matched_orig and r_idx not in matched_rem:
            matched_pairs.append((orig_shapes[o_idx], rem_shapes[r_idx]))
            matched_orig.add(o_idx)
            matched_rem.add(r_idx)

    return matched_pairs


def check_rule2_alignment_preservation(
    orig: Optional[SlideData],
    rem: Optional[SlideData],
    slide_index: int,
    tolerance_emu: int = 45720,  # 0.05 inch = 45720 EMU
) -> List[Issue]:
    """
    RULE 2: Alignment / Layout Preservation
    Every element in the REMEDIATED must be at the same position as in the ORIGINAL.
    - Left, top, width, height (in EMU) with tolerance
    - Rotation
    - Text paragraph alignment (left/center/right/justify)
    - Vertical anchor
    - Z-order (stacking order)
    Reports mismatches with original value, remediated value, and difference.
    """
    issues: List[Issue] = []

    if orig is None or rem is None:
        return issues

    matched_pairs = _match_shapes_between_slides(orig.shapes, rem.shapes)

    for orig_s, rem_s in matched_pairs:
        element_name = rem_s.name
        o_box = BoundingBox(orig_s.left_emu, orig_s.top_emu, orig_s.width_emu, orig_s.height_emu)
        r_box = BoundingBox(rem_s.left_emu, rem_s.top_emu, rem_s.width_emu, rem_s.height_emu)

        # 1. Left Position
        diff_left = rem_s.left_emu - orig_s.left_emu
        if abs(diff_left) > tolerance_emu:
            issues.append(
                Issue(
                    slide_num=slide_index,
                    element_name=element_name,
                    rule_type=RuleType.ALIGNMENT,
                    issue_type="Shifted Position (Left)",
                    description=f"Horizontal position shifted beyond {tolerance_emu} EMU tolerance.",
                    original_value=f"{orig_s.left_emu} EMU ({orig_s.left_emu / 914400:.3f}\")",
                    remediated_value=f"{rem_s.left_emu} EMU ({rem_s.left_emu / 914400:.3f}\")",
                    difference=f"{diff_left:+d} EMU ({diff_left / 914400:+.3f}\")",
                    is_error=True,
                    orig_box=o_box,
                    rem_box=r_box,
                )
            )

        # 2. Top Position
        diff_top = rem_s.top_emu - orig_s.top_emu
        if abs(diff_top) > tolerance_emu:
            issues.append(
                Issue(
                    slide_num=slide_index,
                    element_name=element_name,
                    rule_type=RuleType.ALIGNMENT,
                    issue_type="Shifted Position (Top)",
                    description=f"Vertical position shifted beyond {tolerance_emu} EMU tolerance.",
                    original_value=f"{orig_s.top_emu} EMU ({orig_s.top_emu / 914400:.3f}\")",
                    remediated_value=f"{rem_s.top_emu} EMU ({rem_s.top_emu / 914400:.3f}\")",
                    difference=f"{diff_top:+d} EMU ({diff_top / 914400:+.3f}\")",
                    is_error=True,
                    orig_box=o_box,
                    rem_box=r_box,
                )
            )

        # 3. Width
        diff_w = rem_s.width_emu - orig_s.width_emu
        if abs(diff_w) > tolerance_emu:
            issues.append(
                Issue(
                    slide_num=slide_index,
                    element_name=element_name,
                    rule_type=RuleType.ALIGNMENT,
                    issue_type="Resized Shape (Width)",
                    description=f"Width resized beyond {tolerance_emu} EMU tolerance.",
                    original_value=f"{orig_s.width_emu} EMU ({orig_s.width_emu / 914400:.3f}\")",
                    remediated_value=f"{rem_s.width_emu} EMU ({rem_s.width_emu / 914400:.3f}\")",
                    difference=f"{diff_w:+d} EMU ({diff_w / 914400:+.3f}\")",
                    is_error=True,
                    orig_box=o_box,
                    rem_box=r_box,
                )
            )

        # 4. Height
        diff_h = rem_s.height_emu - orig_s.height_emu
        if abs(diff_h) > tolerance_emu:
            issues.append(
                Issue(
                    slide_num=slide_index,
                    element_name=element_name,
                    rule_type=RuleType.ALIGNMENT,
                    issue_type="Resized Shape (Height)",
                    description=f"Height resized beyond {tolerance_emu} EMU tolerance.",
                    original_value=f"{orig_s.height_emu} EMU ({orig_s.height_emu / 914400:.3f}\")",
                    remediated_value=f"{rem_s.height_emu} EMU ({rem_s.height_emu / 914400:.3f}\")",
                    difference=f"{diff_h:+d} EMU ({diff_h / 914400:+.3f}\")",
                    is_error=True,
                    orig_box=o_box,
                    rem_box=r_box,
                )
            )

        # 5. Rotation
        diff_rot = rem_s.rotation - orig_s.rotation
        if abs(diff_rot) > 1.0:
            issues.append(
                Issue(
                    slide_num=slide_index,
                    element_name=element_name,
                    rule_type=RuleType.ALIGNMENT,
                    issue_type="Changed Rotation",
                    description="Shape rotation angle was altered.",
                    original_value=f"{orig_s.rotation:.1f}°",
                    remediated_value=f"{rem_s.rotation:.1f}°",
                    difference=f"{diff_rot:+.1f}°",
                    is_error=True,
                    orig_box=o_box,
                    rem_box=r_box,
                )
            )

        # 6. Text Paragraph Alignment (ignore blank or whitespace-only paragraphs)
        orig_paras = [p for p in orig_s.paragraphs if normalize_text(p.text)]
        rem_paras = [p for p in rem_s.paragraphs if normalize_text(p.text)]
        for p_idx, (p_orig, p_rem) in enumerate(zip(orig_paras, rem_paras), start=1):
            if p_orig.alignment != p_rem.alignment:
                issues.append(
                    Issue(
                        slide_num=slide_index,
                        element_name=f"{element_name} (Paragraph {p_idx})",
                        rule_type=RuleType.ALIGNMENT,
                        issue_type="Changed Text Alignment",
                        description="Text paragraph alignment changed.",
                        original_value=p_orig.alignment,
                        remediated_value=p_rem.alignment,
                        difference=f"{p_orig.alignment} -> {p_rem.alignment}",
                        is_error=True,
                        orig_box=o_box,
                        rem_box=r_box,
                    )
                )

        # 7. Vertical Anchor (only checked when shapes contain text)
        if normalize_text(orig_s.text) and normalize_text(rem_s.text):
            if orig_s.vertical_anchor and rem_s.vertical_anchor:
                if orig_s.vertical_anchor != rem_s.vertical_anchor:
                    issues.append(
                        Issue(
                            slide_num=slide_index,
                            element_name=element_name,
                            rule_type=RuleType.ALIGNMENT,
                            issue_type="Changed Vertical Anchor",
                            description="Vertical text alignment anchor changed.",
                            original_value=orig_s.vertical_anchor,
                            remediated_value=rem_s.vertical_anchor,
                            difference=f"{orig_s.vertical_anchor} -> {rem_s.vertical_anchor}",
                            is_error=True,
                            orig_box=o_box,
                            rem_box=r_box,
                        )
                    )

        # 8. Z-Order (Stacking Order)
        diff_z = rem_s.z_order - orig_s.z_order
        if abs(diff_z) >= 1:
            issues.append(
                Issue(
                    slide_num=slide_index,
                    element_name=element_name,
                    rule_type=RuleType.ALIGNMENT,
                    issue_type="Changed Z-Order",
                    description="Shape stacking z-order changed.",
                    original_value=f"Z-Index {orig_s.z_order}",
                    remediated_value=f"Z-Index {rem_s.z_order}",
                    difference=f"{diff_z:+d}",
                    is_error=True,
                    orig_box=o_box,
                    rem_box=r_box,
                )
            )

    return issues


def check_rule3_font_preservation(
    orig: Optional[SlideData],
    rem: Optional[SlideData],
    slide_index: int,
) -> List[Issue]:
    """
    Check font preservation between original and remediated slides.
    Detects changes in:
    - Font size (in points, tolerance 0.5 pt)
    - Font typeface / name
    - Font bold / italic style
    """
    issues: List[Issue] = []
    if orig is None or rem is None:
        return issues

    matched_pairs = _match_shapes_between_slides(orig.shapes, rem.shapes)

    for orig_s, rem_s in matched_pairs:
        if not (normalize_text(orig_s.text) and normalize_text(rem_s.text)):
            continue

        o_box = BoundingBox(orig_s.left_emu, orig_s.top_emu, orig_s.width_emu, orig_s.height_emu)
        r_box = BoundingBox(rem_s.left_emu, rem_s.top_emu, rem_s.width_emu, rem_s.height_emu)
        element_name = rem_s.name

        # 1. Font size change
        if orig_s.font_size_pt is not None and rem_s.font_size_pt is not None:
            diff_size = rem_s.font_size_pt - orig_s.font_size_pt
            if abs(diff_size) >= 0.5:
                issues.append(
                    Issue(
                        slide_num=slide_index,
                        element_name=element_name,
                        rule_type=RuleType.FONT,
                        issue_type="Changed Font Size",
                        description=f"Font size changed from {orig_s.font_size_pt} pt to {rem_s.font_size_pt} pt.",
                        original_value=f"{orig_s.font_size_pt} pt",
                        remediated_value=f"{rem_s.font_size_pt} pt",
                        difference=f"{diff_size:+.1f} pt",
                        is_error=True,
                        orig_box=o_box,
                        rem_box=r_box,
                    )
                )

        # 2. Font typeface / name change
        if orig_s.font_name and rem_s.font_name:
            if orig_s.font_name.strip().lower() != rem_s.font_name.strip().lower():
                issues.append(
                    Issue(
                        slide_num=slide_index,
                        element_name=element_name,
                        rule_type=RuleType.FONT,
                        issue_type="Changed Font Typeface",
                        description=f"Font family changed from '{orig_s.font_name}' to '{rem_s.font_name}'.",
                        original_value=orig_s.font_name,
                        remediated_value=rem_s.font_name,
                        difference=f"{orig_s.font_name} -> {rem_s.font_name}",
                        is_error=True,
                        orig_box=o_box,
                        rem_box=r_box,
                    )
                )

        # 3. Bold style change
        if orig_s.is_bold is not None and rem_s.is_bold is not None:
            if orig_s.is_bold != rem_s.is_bold:
                issues.append(
                    Issue(
                        slide_num=slide_index,
                        element_name=element_name,
                        rule_type=RuleType.FONT,
                        issue_type="Changed Font Bold Style",
                        description=f"Font bold style changed (was {orig_s.is_bold}, now {rem_s.is_bold}).",
                        original_value="Bold" if orig_s.is_bold else "Normal",
                        remediated_value="Bold" if rem_s.is_bold else "Normal",
                        difference=f"{'Bold' if orig_s.is_bold else 'Normal'} -> {'Bold' if rem_s.is_bold else 'Normal'}",
                        is_error=True,
                        orig_box=o_box,
                        rem_box=r_box,
                    )
                )

        # 4. Italic style change
        if orig_s.is_italic is not None and rem_s.is_italic is not None:
            if orig_s.is_italic != rem_s.is_italic:
                issues.append(
                    Issue(
                        slide_num=slide_index,
                        element_name=element_name,
                        rule_type=RuleType.FONT,
                        issue_type="Changed Font Italic Style",
                        description=f"Font italic style changed (was {orig_s.is_italic}, now {rem_s.is_italic}).",
                        original_value="Italic" if orig_s.is_italic else "Normal",
                        remediated_value="Italic" if rem_s.is_italic else "Normal",
                        difference=f"{'Italic' if orig_s.is_italic else 'Normal'} -> {'Italic' if rem_s.is_italic else 'Normal'}",
                        is_error=True,
                        orig_box=o_box,
                        rem_box=r_box,
                    )
                )

        # 5. Underline change
        if orig_s.is_underline is not None and rem_s.is_underline is not None:
            if orig_s.is_underline != rem_s.is_underline:
                issues.append(
                    Issue(
                        slide_num=slide_index,
                        element_name=element_name,
                        rule_type=RuleType.FONT,
                        issue_type="Changed Font Underline",
                        description=f"Font underline changed (was {orig_s.is_underline}, now {rem_s.is_underline}).",
                        original_value="Underline" if orig_s.is_underline else "None",
                        remediated_value="Underline" if rem_s.is_underline else "None",
                        difference=f"{'Underline' if orig_s.is_underline else 'None'} -> {'Underline' if rem_s.is_underline else 'None'}",
                        is_error=True,
                        orig_box=o_box,
                        rem_box=r_box,
                    )
                )

        # 6. Color change
        if orig_s.color_hex and rem_s.color_hex:
            if orig_s.color_hex.upper() != rem_s.color_hex.upper():
                issues.append(
                    Issue(
                        slide_num=slide_index,
                        element_name=element_name,
                        rule_type=RuleType.FONT,
                        issue_type="Changed Font Color",
                        description=f"Font color changed from #{orig_s.color_hex} to #{rem_s.color_hex}.",
                        original_value=f"#{orig_s.color_hex}",
                        remediated_value=f"#{rem_s.color_hex}",
                        difference=f"#{orig_s.color_hex} -> #{rem_s.color_hex}",
                        is_error=True,
                        orig_box=o_box,
                        rem_box=r_box,
                    )
                )

    return issues
