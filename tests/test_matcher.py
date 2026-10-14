from __future__ import annotations

from core.matcher import compute_slide_similarity, match_slides
from core.models import SlideData


def test_similarity_identical_slides():
    s1 = SlideData(
        slide_id=1,
        slide_index=1,
        title="Revenue Analysis",
        text_content="Quarterly revenue reached 10 million dollars.",
        shapes_count=3,
    )
    s2 = SlideData(
        slide_id=2,
        slide_index=1,
        title="Revenue Analysis",
        text_content="Quarterly revenue reached 10 million dollars.",
        shapes_count=3,
    )
    sim = compute_slide_similarity(s1, s2)
    assert sim >= 95.0


def test_match_slides_detects_added_and_deleted():
    s_orig_1 = SlideData(slide_id=1, slide_index=1, title="Introduction", text_content="Intro text")
    s_orig_2 = SlideData(slide_id=2, slide_index=2, title="Old Methods", text_content="Archived data")

    s_rem_1 = SlideData(slide_id=10, slide_index=1, title="Introduction", text_content="Intro text")
    s_rem_3 = SlideData(slide_id=11, slide_index=2, title="Brand New Slide", text_content="Completely new content")

    matches = match_slides([s_orig_1, s_orig_2], [s_rem_1, s_rem_3])

    # Should match slide 1 -> slide 1
    match_1 = next((m for m in matches if m.rem_index == 1), None)
    assert match_1 is not None
    assert match_1.orig_index == 1
    assert match_1.match_type == "MATCHED"

    # Should flag rem slide 2 as ADDED
    match_added = next((m for m in matches if m.rem_index == 2), None)
    assert match_added is not None
    assert match_added.match_type == "ADDED"

    # Should flag orig slide 2 as DELETED
    match_deleted = next((m for m in matches if m.orig_index == 2 and m.rem_index is None), None)
    assert match_deleted is not None
    assert match_deleted.match_type == "DELETED"
