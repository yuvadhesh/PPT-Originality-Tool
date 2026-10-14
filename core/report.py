from __future__ import annotations

import math
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import openpyxl
from jinja2 import Template
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from core.models import DeckComparisonResult, Issue, RuleType, SlideStatus

HEADER_FILL = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

ERROR_FILL = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
ERROR_FONT = Font(name="Calibri", size=10, bold=True, color="991B1B")

INFO_FILL = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
INFO_FONT = Font(name="Calibri", size=10, bold=False, color="1E40AF")

PASS_FILL = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
PASS_FONT = Font(name="Calibri", size=10, bold=True, color="166534")

FAIL_FILL = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
FAIL_FONT = Font(name="Calibri", size=10, bold=True, color="991B1B")

# Rule column color codes
RULE_CONTENT_FILL = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
RULE_CONTENT_FONT = Font(name="Calibri", size=10, bold=True, color="92400E")

RULE_ALIGN_FILL = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
RULE_ALIGN_FONT = Font(name="Calibri", size=10, bold=True, color="1E40AF")

RULE_FONT_FILL = PatternFill(start_color="F3E8FF", end_color="F3E8FF", fill_type="solid")
RULE_FONT_FONT = Font(name="Calibri", size=10, bold=True, color="6B21A8")

THIN_BORDER = Border(
    left=Side(style="thin", color="E2E8F0"),
    right=Side(style="thin", color="E2E8F0"),
    top=Side(style="thin", color="E2E8F0"),
    bottom=Side(style="thin", color="E2E8F0"),
)


def export_excel_report(
    result: DeckComparisonResult,
    output_path: str | Path,
    screenshots_map: Optional[Dict[int, Path]] = None,
    orig_pptx_path: Optional[str | Path] = None,
    rem_pptx_path: Optional[str | Path] = None,
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> Path:
    """
    Generate Excel workbook with:
    - Sheet 'Summary': Total issues per rule (Content, Alignment, Font), per-slide Pass/Fail table.
    - Sheet 'Issues': Issue #, Slide No, Rule, Element Name, Description, Original Value,
                      Remediated Value, Difference, Severity, Screenshot Ref (hyperlink).
    - Sheet 'Screenshots': One block per failing slide with bold heading and embedded
                           highlighted combined image.
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    temp_screenshots_dir: Optional[Path] = None

    # If screenshots_map not supplied but presentations given, generate screenshots
    if screenshots_map is None and orig_pptx_path and rem_pptx_path:
        try:
            from core.screenshot_annotator import generate_deck_highlighted_screenshots
            temp_screenshots_dir = Path(tempfile.mkdtemp(prefix="excel_shots_"))
            screenshots_map = generate_deck_highlighted_screenshots(
                result=result,
                orig_pptx_path=orig_pptx_path,
                rem_pptx_path=rem_pptx_path,
                output_dir=temp_screenshots_dir,
                progress_callback=progress_callback,
            )
        except Exception:
            screenshots_map = {}

    wb = openpyxl.Workbook()

    # -------------------------------------------------------------------------
    # 1. Summary Sheet
    # -------------------------------------------------------------------------
    ws_summary = wb.active
    ws_summary.title = "Summary"
    ws_summary.views.sheetView[0].showGridLines = True

    ws_summary.merge_cells("A1:E1")
    t_cell = ws_summary["A1"]
    t_cell.value = "PPT Content, Alignment & Font QA Report"
    t_cell.font = Font(name="Calibri", size=16, bold=True, color="1E293B")
    ws_summary.row_dimensions[1].height = 28

    ws_summary["A2"] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ws_summary["A2"].font = Font(name="Calibri", size=10, italic=True, color="64748B")

    # Overview Metrics Table
    checks_run_str = "Content, Alignment, Font" if getattr(result, "check_fonts", False) else "Content, Alignment"
    meta_rows = [
        ("Checks Run", checks_run_str),
        ("Original File", result.orig_filename),
        ("Remediated File", result.rem_filename),
        ("Original Slides", result.orig_metadata.slide_count),
        ("Remediated Slides", result.rem_metadata.slide_count),
        ("Total Content Issues (Rule 1)", len(result.rule1_content_issues)),
        ("Total Alignment Issues (Rule 2)", len(result.rule2_alignment_issues)),
    ]
    if getattr(result, "check_fonts", False):
        meta_rows.append(("Total Font Issues", len(result.font_issues)))
    meta_rows.extend([
        ("Total Errors", result.total_errors_count),
        ("Passed Slides", result.pass_slides_count),
        ("Failed Slides", result.fail_slides_count),
    ])

    for idx, (lbl, val) in enumerate(meta_rows, start=5):
        ws_summary[f"A{idx}"] = lbl
        ws_summary[f"A{idx}"].font = Font(name="Calibri", size=11, bold=True, color="334155")
        ws_summary[f"B{idx}"] = val
        ws_summary[f"B{idx}"].font = Font(name="Calibri", size=11, color="0F172A")
        ws_summary[f"A{idx}"].border = THIN_BORDER
        ws_summary[f"B{idx}"].border = THIN_BORDER

    # Per-Slide Pass/Fail Table
    start_table_row = len(meta_rows) + 7
    ws_summary.cell(row=start_table_row, column=1, value="Per-Slide Status Overview").font = Font(
        name="Calibri", size=13, bold=True, color="1E293B"
    )

    include_fonts = getattr(result, "check_fonts", False)
    if include_fonts:
        tbl_headers = ["Slide No", "Slide Title", "Status", "Content Issues", "Alignment Issues", "Font Issues"]
    else:
        tbl_headers = ["Slide No", "Slide Title", "Status", "Content Issues", "Alignment Issues"]
    ws_summary.row_dimensions[start_table_row + 1].height = 22

    for c_idx, h_text in enumerate(tbl_headers, start=1):
        cell = ws_summary.cell(row=start_table_row + 1, column=c_idx, value=h_text)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER

    curr_row = start_table_row + 2
    for s_res in result.slide_results:
        s_num = s_res.rem_index if s_res.rem_index is not None else s_res.orig_index or 0
        s_title = getattr(s_res, "slide_key", f"Slide {s_num}")

        row_vals = [
            f"Slide {s_num}",
            s_title,
            s_res.status.value,
            len(s_res.content_issues),
            len(s_res.alignment_issues),
        ]
        if include_fonts:
            row_vals.append(len(s_res.font_issues))

        for col_idx, val in enumerate(row_vals, start=1):
            c = ws_summary.cell(row=curr_row, column=col_idx, value=val)
            c.border = THIN_BORDER
            c.alignment = Alignment(horizontal="center" if col_idx in ([1, 3, 4, 5, 6] if include_fonts else [1, 3, 4, 5]) else "left", vertical="center")
            if col_idx == 3:
                c.fill = PASS_FILL if s_res.status == SlideStatus.PASS else FAIL_FILL
                c.font = PASS_FONT if s_res.status == SlideStatus.PASS else FAIL_FONT

        curr_row += 1

    # -------------------------------------------------------------------------
    # 2. Screenshots Sheet (Build first to determine anchor rows for hyperlinks)
    # -------------------------------------------------------------------------
    ws_screenshots = wb.create_sheet(title="Screenshots")
    ws_screenshots.views.sheetView[0].showGridLines = True

    slide_heading_rows: Dict[int, int] = {}
    if include_fonts:
        failing_slides_with_issues = [
            s for s in result.slide_results
            if s.status == SlideStatus.FAIL and any(i.is_error for i in s.issues)
        ]
    else:
        failing_slides_with_issues = [
            s for s in result.slide_results
            if s.status == SlideStatus.FAIL and any(i.rule_type != RuleType.FONT and i.is_error for i in s.issues)
        ]

    shot_row = 1
    if screenshots_map and failing_slides_with_issues:
        for s_res in failing_slides_with_issues:
            s_num = s_res.rem_index or s_res.orig_index or 1
            img_val = screenshots_map.get(s_num)

            # Record heading row for hyperlink reference
            slide_heading_rows[s_num] = shot_row

            # Issues on this slide
            relevant_issues = [
                i for i in s_res.issues
                if (include_fonts or i.rule_type != RuleType.FONT)
            ]
            issue_nums = [str(i.issue_num) for i in relevant_issues if i.issue_num]
            issue_str = ", ".join(f"#{n}" for n in issue_nums) if issue_nums else ""

            # Slide Heading: "Slide N - Issues: #3, #4" (Never write Pass, no (#1) label)
            heading_title = f"Slide {s_num} - Issues: {issue_str}" if issue_str else f"Slide {s_num} - Issues: None"
            h_cell = ws_screenshots.cell(
                row=shot_row,
                column=1,
                value=heading_title,
            )
            h_cell.font = Font(name="Calibri", size=14, bold=True, color="1E293B")
            ws_screenshots.row_dimensions[shot_row].height = 28

            if isinstance(img_val, (str, Path)) and Path(str(img_val)).exists():
                try:
                    xl_img = XLImage(str(img_val))
                    ws_screenshots.add_image(xl_img, f"A{shot_row + 1}")

                    # Calculate row height spacing from real image height so blocks never overlap
                    # rows = image height / 20 px
                    img_h = getattr(xl_img, "height", 450)
                    rows_spanned = int(math.ceil(img_h / 20.0))
                    shot_row += rows_spanned + 2
                except Exception:
                    ws_screenshots.cell(row=shot_row + 1, column=1, value="[Image could not be embedded]").font = Font(
                        italic=True, color="64748B"
                    )
                    shot_row += 3
            elif isinstance(img_val, str) and img_val.startswith("Render failed"):
                fail_cell = ws_screenshots.cell(row=shot_row + 1, column=1, value=img_val)
                fail_cell.font = Font(name="Calibri", size=12, bold=True, color="DC2626")
                shot_row += 3
            else:
                ws_screenshots.cell(row=shot_row + 1, column=1, value="Location not available").font = Font(
                    italic=True, color="64748B"
                )
                shot_row += 3
    else:
        ws_screenshots.cell(row=1, column=1, value="No screenshots available (all slides passed or rendering was not requested).").font = Font(
            italic=True, color="64748B"
        )

    # -------------------------------------------------------------------------
    # 3. Issues Sheet
    # -------------------------------------------------------------------------
    ws_issues = wb.create_sheet(title="Issues")
    ws_issues.views.sheetView[0].showGridLines = True

    issues_headers = [
        "Issue #",
        "Slide No",
        "Rule",
        "Element Name",
        "Description",
        "Original Value",
        "Remediated Value",
        "Difference",
        "Severity",
        "Screenshot Ref",
    ]
    ws_issues.append(issues_headers)
    ws_issues.row_dimensions[1].height = 26

    for col in range(1, len(issues_headers) + 1):
        cell = ws_issues.cell(row=1, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Freeze top row
    ws_issues.freeze_panes = "A2"

    issues_to_export = result.all_issues if include_fonts else [i for i in result.all_issues if i.rule_type != RuleType.FONT]

    for iss in issues_to_export:
        s_num = iss.slide_num
        row_vals = [
            f"#{iss.issue_num}" if iss.issue_num else "-",
            f"Slide {s_num}" if isinstance(s_num, int) else str(s_num),
            iss.rule_type.value,
            iss.element_name,
            iss.description,
            iss.original_value,
            iss.remediated_value,
            iss.difference,
            "Error" if iss.is_error else "Info",
            "",  # Screenshot Ref filled below
        ]
        ws_issues.append(row_vals)
        cur_r = ws_issues.max_row
        ws_issues.row_dimensions[cur_r].height = 22

        # Issue #
        ws_issues.cell(row=cur_r, column=1).alignment = Alignment(horizontal="center", vertical="center")
        # Slide No
        ws_issues.cell(row=cur_r, column=2).alignment = Alignment(horizontal="center", vertical="center")

        # Rule Column Color Coding
        rule_c = ws_issues.cell(row=cur_r, column=3)
        rule_c.alignment = Alignment(horizontal="center", vertical="center")
        if iss.rule_type == RuleType.CONTENT:
            rule_c.fill = RULE_CONTENT_FILL
            rule_c.font = RULE_CONTENT_FONT
        elif iss.rule_type == RuleType.ALIGNMENT:
            rule_c.fill = RULE_ALIGN_FILL
            rule_c.font = RULE_ALIGN_FONT
        elif iss.rule_type == RuleType.FONT:
            rule_c.fill = RULE_FONT_FILL
            rule_c.font = RULE_FONT_FONT

        # Wrap text on text fields
        for col_idx in [4, 5, 6, 7, 8]:
            ws_issues.cell(row=cur_r, column=col_idx).alignment = Alignment(vertical="center", wrap_text=True)

        # Severity
        sev_c = ws_issues.cell(row=cur_r, column=9)
        sev_c.alignment = Alignment(horizontal="center", vertical="center")
        if iss.is_error:
            sev_c.fill = ERROR_FILL
            sev_c.font = ERROR_FONT
        else:
            sev_c.fill = INFO_FILL
            sev_c.font = INFO_FONT

        # Screenshot Ref Hyperlink
        ref_c = ws_issues.cell(row=cur_r, column=10)
        ref_c.alignment = Alignment(horizontal="center", vertical="center")

        target_row = slide_heading_rows.get(s_num) if isinstance(s_num, int) else None
        if target_row:
            ref_c.value = f"View Slide {s_num}"
            ref_c.hyperlink = f"#'Screenshots'!A{target_row}"
            ref_c.font = Font(name="Calibri", size=10, color="2563EB", underline="single")
        else:
            ref_c.value = "Location not available"
            ref_c.font = Font(name="Calibri", size=10, italic=True, color="64748B")

        for col in range(1, len(issues_headers) + 1):
            ws_issues.cell(row=cur_r, column=col).border = THIN_BORDER

    # Autofilter on Issues sheet
    ws_issues.auto_filter.ref = ws_issues.dimensions

    # -------------------------------------------------------------------------
    # Auto-adjust Column Widths across all sheets
    # -------------------------------------------------------------------------
    for ws in [ws_summary, ws_issues]:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                if len(val) > max_len and "\n" not in val:
                    max_len = len(val)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 11), 50)

    # Save workbook
    wb.save(str(out_file))

    # Clean up temp screenshot directory
    if temp_screenshots_dir and temp_screenshots_dir.exists():
        try:
            shutil.rmtree(temp_screenshots_dir, ignore_errors=True)
        except Exception:
            pass

    return out_file


HTML_REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PPT Compare & QA Report</title>
<style>
  :root {
    --bg: #0F172A;
    --card-bg: #1E293B;
    --card-border: #334155;
    --text: #F8FAFC;
    --text-muted: #94A3B8;
    --error: #EF4444;
    --pass: #22C55E;
    --info: #3B82F6;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background-color: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    line-height: 1.5;
    padding: 2rem;
  }
  .container { max-width: 1200px; margin: 0 auto; }
  .header {
    background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 2rem;
    margin-bottom: 2rem;
  }
  .header h1 { font-size: 2rem; color: #38BDF8; margin-bottom: 0.5rem; }
  .grid-metrics {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
  }
  .card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 10px;
    padding: 1.25rem;
    text-align: center;
  }
  .card .num { font-size: 2.2rem; font-weight: 800; }
  .card .label { font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; }
  .num-err { color: var(--error); }
  .num-pass { color: var(--pass); }
  .num-info { color: var(--info); }
  
  .section-title { font-size: 1.3rem; margin: 2rem 0 1rem; color: #E2E8F0; }
  table {
    width: 100%;
    border-collapse: collapse;
    background: var(--card-bg);
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 2rem;
  }
  th, td { padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--card-border); }
  th { background: #111827; color: var(--text-muted); font-size: 0.85rem; text-transform: uppercase; }
  
  .badge {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 700;
  }
  .badge-error { background: rgba(239, 68, 68, 0.2); color: #FCA5A5; border: 1px solid #EF4444; }
  .badge-info { background: rgba(59, 130, 246, 0.2); color: #93C5FD; border: 1px solid #3B82F6; }
  .badge-pass { background: rgba(34, 197, 94, 0.2); color: #86EFAC; border: 1px solid #22C55E; }
  .badge-fail { background: rgba(239, 68, 68, 0.2); color: #FCA5A5; border: 1px solid #EF4444; }
  .val-diff { font-family: monospace; color: #F87171; font-weight: 600; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>PPT QA Comparison Report</h1>
    <p style="color: var(--text-muted)">Original: <strong>{{ result.orig_filename }}</strong> | Remediated: <strong>{{ result.rem_filename }}</strong></p>
    <p style="color: var(--text-muted); margin-top: 0.25rem">Checks Run: <strong>{{ "Content, Alignment, Font" if result.check_fonts else "Content, Alignment" }}</strong></p>
    <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.5rem">Report generated: {{ timestamp }}</p>
  </div>

  <div class="grid-metrics">
    <div class="card">
      <div class="num num-err">{{ result.rule1_errors_count }}</div>
      <div class="label">Rule 1: Content Issues</div>
    </div>
    <div class="card">
      <div class="num num-err">{{ result.rule2_errors_count }}</div>
      <div class="label">Rule 2: Alignment Issues</div>
    </div>
    {% if result.check_fonts %}
    <div class="card">
      <div class="num num-info">{{ result.font_errors_count }}</div>
      <div class="label">Font Issues</div>
    </div>
    {% endif %}
    <div class="card">
      <div class="num num-pass">{{ result.pass_slides_count }}</div>
      <div class="label">Passed Slides</div>
    </div>
    <div class="card">
      <div class="num num-err">{{ result.fail_slides_count }}</div>
      <div class="label">Failed Slides</div>
    </div>
  </div>

  <h2 class="section-title">All Comparison Issues</h2>
  <table>
    <thead>
      <tr>
        <th>Issue #</th>
        <th>Slide</th>
        <th>Rule</th>
        <th>Element</th>
        <th>Severity</th>
        <th>Description</th>
        <th>Original</th>
        <th>Remediated</th>
        <th>Difference</th>
      </tr>
    </thead>
    <tbody>
      {% for iss in result.all_issues %}
      <tr>
        <td><strong>#{{ iss.issue_num or loop.index }}</strong></td>
        <td>Slide {{ iss.slide_num }}</td>
        <td>{{ iss.rule_type.value }}</td>
        <td>{{ iss.element_name }}</td>
        <td><span class="badge {% if iss.is_error %}badge-error{% else %}badge-info{% endif %}">{{ "Error" if iss.is_error else "Info" }}</span></td>
        <td>{{ iss.description }}</td>
        <td style="font-family: monospace; font-size: 0.85rem">{{ iss.original_value }}</td>
        <td style="font-family: monospace; font-size: 0.85rem">{{ iss.remediated_value }}</td>
        <td class="val-diff">{{ iss.difference }}</td>
      </tr>
      {% endfor %}
      {% if not result.all_issues %}
      <tr><td colspan="9" style="text-align: center; color: var(--text-muted)">No issues detected! Presentations match perfectly.</td></tr>
      {% endif %}
    </tbody>
  </table>
</div>
</body>
</html>
"""


def export_html_report(result: DeckComparisonResult, output_path: Optional[str | Path] = None) -> str:
    """Generate HTML comparison report."""
    template = Template(HTML_REPORT_TEMPLATE)
    html_out = template.render(
        result=result,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(html_out, encoding="utf-8")
    return html_out
