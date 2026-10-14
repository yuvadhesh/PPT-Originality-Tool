from __future__ import annotations

from core.comparator import compare_presentations
from core.models import RuleType, SlideStatus


def test_comparator_default_check_fonts_false(sample_decks, tmp_path):
    orig_path, rem_path = sample_decks

    # By default, check_fonts is False
    result = compare_presentations(
        orig_path=orig_path,
        rem_path=rem_path,
        enable_visual_preview=False,
        output_dir=tmp_path / "preview_out_false",
    )

    assert result.check_fonts is False
    assert result.orig_filename == orig_path.name
    assert result.rem_filename == rem_path.name
    assert len(result.slide_results) == 7

    # Slide 1: Clean matching slide -> PASS
    assert result.slide_results[0].status == SlideStatus.PASS

    # Slide 2: Missing text -> FAIL on Rule 1
    assert result.slide_results[1].status == SlideStatus.FAIL

    # Slide 3: Missing image -> FAIL on Rule 1
    assert result.slide_results[2].status == SlideStatus.FAIL

    # Slide 4: Shifted shape -> FAIL on Rule 2
    assert result.slide_results[3].status == SlideStatus.FAIL

    # Slide 5: Resized shape -> FAIL on Rule 2
    assert result.slide_results[4].status == SlideStatus.FAIL

    # Slide 6: Changed text alignment -> FAIL on Rule 2
    assert result.slide_results[5].status == SlideStatus.FAIL

    # Slide 7: Has font change (Arial -> Times New Roman), but check_fonts=False:
    # -> Zero font issues generated and the slide passes!
    slide7_font_issues = [i for i in result.slide_results[6].issues if i.rule_type == RuleType.FONT]
    assert len(slide7_font_issues) == 0
    assert result.slide_results[6].status == SlideStatus.PASS

    # Deck counts when check_fonts is False
    assert len(result.font_issues) == 0
    assert result.font_errors_count == 0
    assert result.pass_slides_count == 2  # Slide 1 and Slide 7 pass
    assert result.fail_slides_count == 5


def test_comparator_check_fonts_true(sample_decks, tmp_path):
    orig_path, rem_path = sample_decks

    result = compare_presentations(
        orig_path=orig_path,
        rem_path=rem_path,
        check_fonts=True,
        enable_visual_preview=False,
        output_dir=tmp_path / "preview_out_true",
    )

    assert result.check_fonts is True

    # Slide 7: Changed font name (Arial -> Times New Roman) with check_fonts=True:
    # -> Font issue reported with correct values and slide fails!
    assert result.slide_results[6].status == SlideStatus.FAIL
    slide7_font_issues = [i for i in result.slide_results[6].issues if i.rule_type == RuleType.FONT]
    assert len(slide7_font_issues) == 1

    font_issue = slide7_font_issues[0]
    assert font_issue.issue_type == "Changed Font Typeface"
    assert font_issue.original_value == "Arial"
    assert font_issue.remediated_value == "Times New Roman"
    assert font_issue.difference == "Arial -> Times New Roman"
    assert font_issue.is_error is True

    # Deck counts when check_fonts is True
    assert len(result.font_issues) == 1
    assert result.font_errors_count == 1
    assert result.pass_slides_count == 1  # Only Slide 1 passes
    assert result.fail_slides_count == 6
