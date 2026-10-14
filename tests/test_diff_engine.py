from __future__ import annotations

from core.diff_engine import (
    check_rule1_content_preservation,
    check_rule2_alignment_preservation,
    check_rule3_font_preservation,
    normalize_text,
)
from core.models import (
    HyperlinkInfo,
    ParagraphInfo,
    RuleType,
    ShapeInfo,
    SlideData,
    TableInfo,
)


def test_rule1_missing_text():
    orig = SlideData(
        slide_id=1,
        slide_index=1,
        text_blocks=["Quarterly revenue exceeded 10 million dollars in regional markets."],
        text_content="Quarterly revenue exceeded 10 million dollars in regional markets.",
    )
    rem = SlideData(
        slide_id=2,
        slide_index=1,
        text_blocks=["Welcome to the report."],
        text_content="Welcome to the report.",
    )

    issues = check_rule1_content_preservation(orig, rem, 1, text_threshold=95.0)
    missing_text_issues = [i for i in issues if i.issue_type == "Missing Text"]
    assert len(missing_text_issues) >= 1
    assert missing_text_issues[0].is_error is True
    assert missing_text_issues[0].rule_type == RuleType.CONTENT


def test_rule1_missing_image():
    orig_img = ShapeInfo(
        shape_id=1, name="ChartImg", shape_type="PICTURE", left_emu=0, top_emu=0, width_emu=100, height_emu=100,
        is_image=True, image_hash="abcdef1234567890",
    )
    orig = SlideData(
        slide_id=1,
        slide_index=1,
        shapes=[orig_img],
        images_count=1,
    )
    rem = SlideData(
        slide_id=2,
        slide_index=1,
        shapes=[],
        images_count=0,
    )

    issues = check_rule1_content_preservation(orig, rem, 1)
    img_issues = [i for i in issues if i.issue_type == "Missing Image"]
    assert len(img_issues) >= 1
    assert img_issues[0].is_error is True


def test_rule1_table_structure_mismatch():
    t_orig = TableInfo(shape_id=1, name="Table1", rows=4, cols=3)
    t_rem = TableInfo(shape_id=1, name="Table1", rows=3, cols=3)

    orig = SlideData(slide_id=1, slide_index=1, tables=[t_orig], tables_count=1)
    rem = SlideData(slide_id=2, slide_index=1, tables=[t_rem], tables_count=1)

    issues = check_rule1_content_preservation(orig, rem, 1)
    table_issues = [i for i in issues if i.issue_type == "Table Rows Mismatch"]
    assert len(table_issues) == 1
    assert table_issues[0].is_error is True
    assert table_issues[0].difference == "-1 rows"


def test_rule1_extra_content_is_info():
    orig = SlideData(slide_id=1, slide_index=1, images_count=1)
    rem = SlideData(slide_id=2, slide_index=1, images_count=2)

    issues = check_rule1_content_preservation(orig, rem, 1)
    extra_issues = [i for i in issues if i.issue_type == "Extra Image"]
    assert len(extra_issues) == 1
    assert extra_issues[0].is_error is False  # Info level, not an error!


def test_rule2_shifted_position_emu():
    # Tolerance is 45720 EMU (0.05 inch)
    s_orig = ShapeInfo(
        shape_id=1, name="Box1", shape_type="RECTANGLE",
        left_emu=914400, top_emu=914400, width_emu=1828800, height_emu=914400,
    )
    # Shifted horizontally by 100000 EMU (> 45720 EMU)
    s_rem = ShapeInfo(
        shape_id=1, name="Box1", shape_type="RECTANGLE",
        left_emu=1014400, top_emu=914400, width_emu=1828800, height_emu=914400,
    )

    orig = SlideData(slide_id=1, slide_index=1, shapes=[s_orig])
    rem = SlideData(slide_id=2, slide_index=1, shapes=[s_rem])

    issues = check_rule2_alignment_preservation(orig, rem, 1, tolerance_emu=45720)
    shift_issues = [i for i in issues if i.issue_type == "Shifted Position (Left)"]
    assert len(shift_issues) == 1
    assert shift_issues[0].is_error is True
    assert shift_issues[0].rule_type == RuleType.ALIGNMENT
    assert "+100000 EMU" in shift_issues[0].difference


def test_rule2_resized_shape_emu():
    s_orig = ShapeInfo(
        shape_id=1, name="Box1", shape_type="RECTANGLE",
        left_emu=914400, top_emu=914400, width_emu=2000000, height_emu=1000000,
    )
    s_rem = ShapeInfo(
        shape_id=1, name="Box1", shape_type="RECTANGLE",
        left_emu=914400, top_emu=914400, width_emu=1500000, height_emu=1000000,
    )

    orig = SlideData(slide_id=1, slide_index=1, shapes=[s_orig])
    rem = SlideData(slide_id=2, slide_index=1, shapes=[s_rem])

    issues = check_rule2_alignment_preservation(orig, rem, 1, tolerance_emu=45720)
    resize_issues = [i for i in issues if i.issue_type == "Resized Shape (Width)"]
    assert len(resize_issues) == 1
    assert resize_issues[0].is_error is True


def test_rule2_changed_text_alignment():
    p_orig = ParagraphInfo(text="Hello", alignment="CENTER")
    p_rem = ParagraphInfo(text="Hello", alignment="LEFT")

    s_orig = ShapeInfo(
        shape_id=1, name="Text1", shape_type="TEXT_BOX",
        left_emu=914400, top_emu=914400, width_emu=914400, height_emu=914400,
        paragraphs=[p_orig],
    )
    s_rem = ShapeInfo(
        shape_id=1, name="Text1", shape_type="TEXT_BOX",
        left_emu=914400, top_emu=914400, width_emu=914400, height_emu=914400,
        paragraphs=[p_rem],
    )

    orig = SlideData(slide_id=1, slide_index=1, shapes=[s_orig])
    rem = SlideData(slide_id=2, slide_index=1, shapes=[s_rem])

    issues = check_rule2_alignment_preservation(orig, rem, 1)
    align_issues = [i for i in issues if i.issue_type == "Changed Text Alignment"]
    assert len(align_issues) == 1
    assert align_issues[0].is_error is True
    assert align_issues[0].original_value == "CENTER"
    assert align_issues[0].remediated_value == "LEFT"


def test_font_change_zero_content_and_alignment_issues_when_font_toggle_off():
    """
    Test: same text, different font (Arial to Times New Roman) and different
    spacing/wrapping gives zero Content issues and zero Alignment issues (font toggle OFF).
    """
    orig_shape = ShapeInfo(
        shape_id=1,
        name="TitleBox",
        shape_type="TEXT_BOX",
        left_emu=914400,
        top_emu=914400,
        width_emu=1828800,
        height_emu=914400,
        text="Chapter 15:\nCyber Detective Investigation",
        font_name="Arial",
        font_size_pt=24.0,
    )
    rem_shape = ShapeInfo(
        shape_id=1,
        name="TitleBox",
        shape_type="TEXT_BOX",
        left_emu=914400,
        top_emu=914400,
        width_emu=1828800,
        height_emu=914400,
        text="Chapter 15: Cyber Detective\nInvestigation",
        font_name="Times New Roman",
        font_size_pt=24.0,
    )

    orig = SlideData(
        slide_id=1,
        slide_index=1,
        shapes=[orig_shape],
        text_blocks=[orig_shape.text],
        text_content=orig_shape.text,
    )
    rem = SlideData(
        slide_id=2,
        slide_index=1,
        shapes=[rem_shape],
        text_blocks=[rem_shape.text],
        text_content=rem_shape.text,
    )

    content_issues = check_rule1_content_preservation(orig, rem, 1)
    alignment_issues = check_rule2_alignment_preservation(orig, rem, 1)

    assert len(content_issues) == 0, f"Expected 0 Content issues, got: {content_issues}"
    assert len(alignment_issues) == 0, f"Expected 0 Alignment issues, got: {alignment_issues}"


def test_font_change_only_font_issues_when_font_toggle_on():
    """
    Test: same font change with the toggle ON gives only Font issues.
    """
    orig_shape = ShapeInfo(
        shape_id=1,
        name="TitleBox",
        shape_type="TEXT_BOX",
        left_emu=914400,
        top_emu=914400,
        width_emu=1828800,
        height_emu=914400,
        text="Chapter 15: Cyber Detective Investigation",
        font_name="Arial",
        font_size_pt=24.0,
    )
    rem_shape = ShapeInfo(
        shape_id=1,
        name="TitleBox",
        shape_type="TEXT_BOX",
        left_emu=914400,
        top_emu=914400,
        width_emu=1828800,
        height_emu=914400,
        text="Chapter 15: Cyber Detective Investigation",
        font_name="Times New Roman",
        font_size_pt=24.0,
    )

    orig = SlideData(
        slide_id=1,
        slide_index=1,
        shapes=[orig_shape],
        text_blocks=[orig_shape.text],
        text_content=orig_shape.text,
    )
    rem = SlideData(
        slide_id=2,
        slide_index=1,
        shapes=[rem_shape],
        text_blocks=[rem_shape.text],
        text_content=rem_shape.text,
    )

    content_issues = check_rule1_content_preservation(orig, rem, 1)
    alignment_issues = check_rule2_alignment_preservation(orig, rem, 1)
    font_issues = check_rule3_font_preservation(orig, rem, 1)

    assert len(content_issues) == 0, f"Expected 0 Content issues, got: {content_issues}"
    assert len(alignment_issues) == 0, f"Expected 0 Alignment issues, got: {alignment_issues}"
    assert len(font_issues) == 1, f"Expected 1 Font issue, got: {font_issues}"
    assert font_issues[0].rule_type == RuleType.FONT
    assert font_issues[0].issue_type == "Changed Font Typeface"
    assert "Times New Roman" in font_issues[0].remediated_value


def test_whitespace_runs_collapse_to_single_space_no_issue():
    """
    Test: 'Concave down' vs 'Concave  down' (two spaces) gives no issue,
    because whitespace runs collapse to one space.
    """
    assert normalize_text("Concave  down") == "Concave down"
    assert normalize_text("Concave \t\n  down") == "Concave down"
    assert normalize_text("Concave\u00A0down") == "Concave down"
    assert normalize_text("  Concave down  ") == "Concave down"

    orig_shape = ShapeInfo(
        shape_id=1,
        name="Box",
        shape_type="TEXT_BOX",
        left_emu=0,
        top_emu=0,
        width_emu=100,
        height_emu=100,
        text="Concave down",
    )
    rem_shape = ShapeInfo(
        shape_id=1,
        name="Box",
        shape_type="TEXT_BOX",
        left_emu=0,
        top_emu=0,
        width_emu=100,
        height_emu=100,
        text="Concave  down",
    )
    orig = SlideData(
        slide_id=1,
        slide_index=1,
        shapes=[orig_shape],
        text_blocks=[orig_shape.text],
        text_content=orig_shape.text,
    )
    rem = SlideData(
        slide_id=2,
        slide_index=1,
        shapes=[rem_shape],
        text_blocks=[rem_shape.text],
        text_content=rem_shape.text,
    )

    issues = check_rule1_content_preservation(orig, rem, 1)
    assert len(issues) == 0, f"Expected 0 issues, got: {issues}"


def test_real_content_difference_reported():
    """
    Test: 'Concave down' vs 'Concave dow' is still reported as a Content issue.
    """
    orig_shape = ShapeInfo(
        shape_id=1,
        name="TitleBox",
        shape_type="TEXT_BOX",
        left_emu=0,
        top_emu=0,
        width_emu=100,
        height_emu=100,
        text="Concave down",
    )
    rem_shape = ShapeInfo(
        shape_id=1,
        name="TitleBox",
        shape_type="TEXT_BOX",
        left_emu=0,
        top_emu=0,
        width_emu=100,
        height_emu=100,
        text="Concave dow",
    )
    orig = SlideData(
        slide_id=1,
        slide_index=1,
        shapes=[orig_shape],
        text_blocks=[orig_shape.text],
        text_content=orig_shape.text,
    )
    rem = SlideData(
        slide_id=2,
        slide_index=1,
        shapes=[rem_shape],
        text_blocks=[rem_shape.text],
        text_content=rem_shape.text,
    )

    issues = check_rule1_content_preservation(orig, rem, 1)
    missing_text_issues = [i for i in issues if i.issue_type == "Missing Text"]
    assert len(missing_text_issues) == 1
    issue = missing_text_issues[0]
    assert issue.is_error is True
    assert issue.rule_type == RuleType.CONTENT
    assert issue.original_value == "Concave down"
    assert "Concave dow" in issue.remediated_value


def test_rule1_speaker_notes_and_hyperlinks_whitespace_ignored():
    """Verify notes and hyperlinks ignore whitespace differences."""
    # Speaker notes differing only by spaces, newlines, tabs
    orig = SlideData(
        slide_id=1,
        slide_index=1,
        notes="Important notes:\n  - Bullet point one\n  - Bullet point two\n",
        hyperlinks=[HyperlinkInfo(text="Click Here", url="  https://example.com/info  ", shape_name="LinkShape")],
    )
    rem = SlideData(
        slide_id=2,
        slide_index=1,
        notes="Important notes: - Bullet point one - Bullet point two",
        hyperlinks=[HyperlinkInfo(text="Click\u00A0Here", url="https://example.com/info", shape_name="LinkShape")],
    )

    issues = check_rule1_content_preservation(orig, rem, 1)
    assert len(issues) == 0


def test_rule1_empty_or_whitespace_only_text_ignored():
    """Empty or whitespace-only text must not be reported as missing or extra."""
    orig = SlideData(
        slide_id=1,
        slide_index=1,
        text_blocks=["   \t\n  \u00A0  "],
        text_content="   \t\n  \u00A0  ",
        shapes=[ShapeInfo(shape_id=1, name="EmptyShape", shape_type="TEXT_BOX", left_emu=0, top_emu=0, width_emu=100, height_emu=100, text="   \t\n  \u00A0  ")],
    )
    rem = SlideData(
        slide_id=2,
        slide_index=1,
        text_blocks=[],
        text_content="",
        shapes=[],
    )

    issues = check_rule1_content_preservation(orig, rem, 1)
    assert len(issues) == 0


def test_rule2_alignment_ignores_blank_paragraphs():
    """Differences caused by extra blank paragraphs must not trigger alignment issues."""
    p1 = ParagraphInfo(text="Header", alignment="CENTER")
    p_blank = ParagraphInfo(text="   \n   ", alignment="LEFT")
    p2 = ParagraphInfo(text="Content", alignment="LEFT")

    orig_s = ShapeInfo(
        shape_id=1, name="Box1", shape_type="TEXT_BOX",
        left_emu=914400, top_emu=914400, width_emu=914400, height_emu=914400,
        text="Header Content",
        paragraphs=[p1, p_blank, p2],
    )
    rem_s = ShapeInfo(
        shape_id=1, name="Box1", shape_type="TEXT_BOX",
        left_emu=914400, top_emu=914400, width_emu=914400, height_emu=914400,
        text="Header Content",
        paragraphs=[p1, p2],
    )

    orig = SlideData(slide_id=1, slide_index=1, shapes=[orig_s])
    rem = SlideData(slide_id=2, slide_index=1, shapes=[rem_s])

    issues = check_rule2_alignment_preservation(orig, rem, 1)
    align_issues = [i for i in issues if i.issue_type == "Changed Text Alignment"]
    assert len(align_issues) == 0


def test_rule1_equation_omml_vs_unicode_text():
    """An equation as OMML in original and plain Unicode in remediated gives no issue."""
    # Orig has OMML math text extracted from m:t (e.g., Mathematical Italic 𝑥² + 𝑦² = 1 or normalized)
    orig_shape = ShapeInfo(
        shape_id=1,
        name="Equation 1",
        shape_type="TEXT_BOX",
        left_emu=1000000,
        top_emu=1000000,
        width_emu=2000000,
        height_emu=500000,
        text="𝑥2 + 𝑦2 = 1",
    )
    rem_shape = ShapeInfo(
        shape_id=2,
        name="Equation 1 Remediated",
        shape_type="TEXT_BOX",
        left_emu=1000000,
        top_emu=1000000,
        width_emu=2000000,
        height_emu=500000,
        text="x2 + y2 = 1",
    )
    orig = SlideData(slide_id=1, slide_index=1, shapes=[orig_shape], text_blocks=[orig_shape.text], text_content=orig_shape.text)
    rem = SlideData(slide_id=2, slide_index=1, shapes=[rem_shape], text_blocks=[rem_shape.text], text_content=rem_shape.text)

    issues = check_rule1_content_preservation(orig, rem, 1)
    missing_text_issues = [i for i in issues if i.issue_type == "Missing Text"]
    assert len(missing_text_issues) == 0


def test_rule1_symbol_font_equation_vs_unicode():
    """Symbol font 'Dq = - 2.00' vs 'Δθ = -2.00' gives no issue."""
    orig_shape = ShapeInfo(
        shape_id=14,
        name="TextBox 14",
        shape_type="TEXT_BOX",
        left_emu=3778904,
        top_emu=4672888,
        width_emu=3164821,
        height_emu=461665,
        text="Dq = – 2.00 revolutions",
    )
    rem_shape = ShapeInfo(
        shape_id=4,
        name="Object 3",
        shape_type="TEXT_BOX",
        left_emu=3886200,
        top_emu=4502403,
        width_emu=6210300,
        height_emu=852487,
        text="Δθ = -2.00 revolutions (2π rad / 1 rev) = -12.6 rad",
    )
    orig = SlideData(slide_id=1, slide_index=1, shapes=[orig_shape], text_blocks=[orig_shape.text], text_content=orig_shape.text)
    rem = SlideData(slide_id=2, slide_index=1, shapes=[rem_shape], text_blocks=[rem_shape.text], text_content=rem_shape.text)

    issues = check_rule1_content_preservation(orig, rem, 1)
    missing_text_issues = [i for i in issues if i.issue_type == "Missing Text"]
    assert len(missing_text_issues) == 0


def test_rule1_really_deleted_text_reported():
    """Text that is truly deleted from original is still reported as Missing Text."""
    orig_shape = ShapeInfo(
        shape_id=1,
        name="WarningBox",
        shape_type="TEXT_BOX",
        left_emu=1000000,
        top_emu=1000000,
        width_emu=2000000,
        height_emu=500000,
        text="Critical Safety Warning: Disconnect electrical power before servicing equipment.",
    )
    rem_shape = ShapeInfo(
        shape_id=2,
        name="TitleBox",
        shape_type="TEXT_BOX",
        left_emu=1000000,
        top_emu=1000000,
        width_emu=2000000,
        height_emu=500000,
        text="Introduction to Laboratory Procedures",
    )
    orig = SlideData(slide_id=1, slide_index=1, shapes=[orig_shape], text_blocks=[orig_shape.text], text_content=orig_shape.text)
    rem = SlideData(slide_id=2, slide_index=1, shapes=[rem_shape], text_blocks=[rem_shape.text], text_content=rem_shape.text)

    issues = check_rule1_content_preservation(orig, rem, 1)
    missing_text_issues = [i for i in issues if i.issue_type == "Missing Text"]
    assert len(missing_text_issues) == 1
    assert missing_text_issues[0].is_error is True
    assert "Critical Safety Warning" in missing_text_issues[0].original_value
    assert "TitleBox" in missing_text_issues[0].remediated_value


def test_rule1_short_text_fewer_than_3_meaningful_chars_ignored():
    """Text with fewer than 3 meaningful characters is ignored to reduce noise."""
    orig_shape = ShapeInfo(
        shape_id=1,
        name="DotShape",
        shape_type="TEXT_BOX",
        left_emu=0,
        top_emu=0,
        width_emu=100,
        height_emu=100,
        text=".-",
    )
    rem = SlideData(slide_id=2, slide_index=1, shapes=[], text_blocks=[], text_content="")
    orig = SlideData(slide_id=1, slide_index=1, shapes=[orig_shape], text_blocks=[orig_shape.text], text_content=orig_shape.text)

    issues = check_rule1_content_preservation(orig, rem, 1)
    missing_text_issues = [i for i in issues if i.issue_type == "Missing Text"]
    assert len(missing_text_issues) == 0


def test_rule1_group_fragment_deduplication():
    """Equation fragments from the same group shape are reported as a single issue."""
    frag1 = ShapeInfo(
        shape_id=10,
        name="Fragment 1",
        shape_type="TEXT_BOX",
        left_emu=100,
        top_emu=100,
        width_emu=100,
        height_emu=100,
        text="deleted numerator term",
        parent_group_id=99,
    )
    frag2 = ShapeInfo(
        shape_id=11,
        name="Fragment 2",
        shape_type="TEXT_BOX",
        left_emu=100,
        top_emu=200,
        width_emu=100,
        height_emu=100,
        text="deleted denominator term",
        parent_group_id=99,
    )
    orig = SlideData(slide_id=1, slide_index=1, shapes=[frag1, frag2], text_blocks=[frag1.text, frag2.text])
    rem = SlideData(slide_id=2, slide_index=1, shapes=[], text_blocks=[])

    issues = check_rule1_content_preservation(orig, rem, 1)
    missing_text_issues = [i for i in issues if i.issue_type == "Missing Text"]
    assert len(missing_text_issues) == 1
    assert "deleted numerator term" in missing_text_issues[0].original_value
    assert "deleted denominator term" in missing_text_issues[0].original_value


