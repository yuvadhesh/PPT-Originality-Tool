from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import streamlit as st
from PIL import Image

from core.comparator import compare_presentations
from core.diff_engine import normalize_text
from core.models import DeckComparisonResult, RuleType, SlideStatus
from core.parser import PresentationParseError, validate_pptx_file
from core.report import export_excel_report, export_html_report
from core.screenshot_annotator import generate_deck_highlighted_screenshots
from core.visual_diff import find_libreoffice_executable, LibreOfficeNotFoundError
import difflib

# -----------------------------------------------------------------------------
# Streamlit Page Config & Theme
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="PPT Compare & QA Checker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
      
      html, body, [class*="css"] {
          font-family: 'Inter', sans-serif;
      }

      .hero-container {
          background: linear-gradient(135deg, #0F172A 0%, #1E293B 50%, #0F172A 100%);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 14px;
          padding: 1.8rem 2.2rem;
          margin-bottom: 1.5rem;
          box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
      }
      .hero-title {
          font-size: 2.2rem;
          font-weight: 800;
          background: linear-gradient(90deg, #38BDF8, #818CF8);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          margin-bottom: 0.3rem;
      }
      .hero-subtitle {
          color: #94A3B8;
          font-size: 1.05rem;
          font-weight: 400;
      }

      .metric-card {
          background: rgba(30, 41, 59, 0.7);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          padding: 1.1rem 0.8rem;
          text-align: center;
          transition: transform 0.2s ease;
      }
      .metric-card:hover {
          transform: translateY(-2px);
          border-color: rgba(56, 189, 248, 0.4);
      }
      .metric-val {
          font-size: 2.2rem;
          font-weight: 800;
          line-height: 1.1;
      }
      .metric-lbl {
          font-size: 0.75rem;
          color: #94A3B8;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          margin-top: 0.3rem;
          font-weight: 600;
      }

      .badge {
          display: inline-block;
          padding: 0.22rem 0.65rem;
          border-radius: 9999px;
          font-size: 0.72rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.04em;
      }
      .badge-error { background: rgba(239, 68, 68, 0.2); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.4); }
      .badge-info { background: rgba(59, 130, 246, 0.2); color: #60A5FA; border: 1px solid rgba(59, 130, 246, 0.4); }
      .badge-pass { background: rgba(34, 197, 94, 0.2); color: #4ADE80; border: 1px solid rgba(34, 197, 94, 0.4); }
      .badge-fail { background: rgba(239, 68, 68, 0.2); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.4); }

      .issue-card {
          background: #1E293B;
          border-left: 4px solid #EF4444;
          border-radius: 0 8px 8px 0;
          padding: 0.9rem 1.1rem;
          margin-bottom: 0.8rem;
      }
      .issue-card.info {
          border-left-color: #3B82F6;
      }
      .issue-top {
          display: flex;
          align-items: center;
          gap: 0.6rem;
          margin-bottom: 0.3rem;
      }
      .issue-title { font-weight: 700; font-size: 0.95rem; color: #F1F5F9; }
      .issue-desc { font-size: 0.88rem; color: #CBD5E1; margin: 0.3rem 0; }
      
      .val-compare {
          display: grid;
          grid-template-columns: 1fr 1fr 1fr;
          gap: 0.8rem;
          background: #0B1120;
          padding: 0.6rem 0.8rem;
          border-radius: 6px;
          font-size: 0.83rem;
          margin-top: 0.4rem;
      }
      .val-label { color: #94A3B8; font-weight: 600; font-size: 0.75rem; text-transform: uppercase; }
      .val-orig { color: #E2E8F0; font-family: monospace; }
      .val-rem { color: #E2E8F0; font-family: monospace; }
      .val-diff { color: #F87171; font-family: monospace; font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_word_level_diff(orig_text: str, rem_text: str) -> Optional[str]:
    """
    Generate word-level text diff where whitespace-only differences
    are NEVER highlighted as changes.
    """
    if not orig_text or not rem_text:
        return None
    if normalize_text(orig_text) == normalize_text(rem_text):
        return None

    words_orig = orig_text.split()
    words_rem = rem_text.split()
    matcher = difflib.SequenceMatcher(
        isjunk=None,
        a=[normalize_text(w) for w in words_orig],
        b=[normalize_text(w) for w in words_rem],
        autojunk=False,
    )
    diff_html_parts = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            diff_html_parts.append(" ".join(words_orig[i1:i2]))
        elif tag == "replace":
            deleted = " ".join(words_orig[i1:i2])
            added = " ".join(words_rem[j1:j2])
            if normalize_text(deleted) != normalize_text(added):
                if deleted:
                    diff_html_parts.append(
                        f'<span style="background: rgba(239, 68, 68, 0.25); color: #FCA5A5; text-decoration: line-through; padding: 1px 4px; border-radius: 3px;">{deleted}</span>'
                    )
                if added:
                    diff_html_parts.append(
                        f'<span style="background: rgba(34, 197, 94, 0.25); color: #86EFAC; padding: 1px 4px; border-radius: 3px;">{added}</span>'
                    )
            else:
                diff_html_parts.append(deleted)
        elif tag == "delete":
            deleted = " ".join(words_orig[i1:i2])
            if normalize_text(deleted):
                diff_html_parts.append(
                    f'<span style="background: rgba(239, 68, 68, 0.25); color: #FCA5A5; text-decoration: line-through; padding: 1px 4px; border-radius: 3px;">{deleted}</span>'
                )
        elif tag == "insert":
            added = " ".join(words_rem[j1:j2])
            if normalize_text(added):
                diff_html_parts.append(
                    f'<span style="background: rgba(34, 197, 94, 0.25); color: #86EFAC; padding: 1px 4px; border-radius: 3px;">{added}</span>'
                )
    return " ".join(diff_html_parts)

# -----------------------------------------------------------------------------
# Sidebar Configuration
# -----------------------------------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/microsoft-powerpoint.png", width=52)
    st.title("Settings")

    try:
        soffice_loc = find_libreoffice_executable()
        st.success(f"✓ LibreOffice Detected")
        soffice_available = True
    except LibreOfficeNotFoundError:
        st.warning("⚠️ LibreOffice not found (Visual preview disabled)")
        soffice_available = False

    st.markdown("---")
    st.subheader("Comparison Parameters")

    text_threshold = st.slider(
        "Rule 1 Text Similarity Threshold (%)",
        min_value=80,
        max_value=100,
        value=95,
        help="Fuzzy match threshold (rapidfuzz) to verify original text presence.",
    )

    tolerance_inch = st.number_input(
        "Rule 2 Alignment Tolerance (inches)",
        min_value=0.01,
        max_value=0.50,
        value=0.05,
        step=0.01,
        format="%.3f",
        help="Tolerance in inches for left, top, width, and height comparisons (default: 0.05\" = 45,720 EMU).",
    )
    tolerance_emu = int(tolerance_inch * 914400)

    enable_preview = st.checkbox(
        "Enable Side-by-Side Visual Preview",
        value=soffice_available,
        disabled=not soffice_available,
        help="Renders slides as images to visually compare positions side-by-side.",
    )

    st.markdown("---")
    st.caption("Checks ONLY:\n1. Content Preservation\n2. Alignment / Layout Preservation")

# -----------------------------------------------------------------------------
# Main Header
# -----------------------------------------------------------------------------
st.markdown(
    """
    <div class="hero-container">
        <div class="hero-title">PPT Compare & QA Checker</div>
        <div class="hero-subtitle">Strict Verification of Content Preservation (Rule 1) & Alignment/Layout Preservation (Rule 2)</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# File Uploads Section
# -----------------------------------------------------------------------------
upload_col1, upload_col2 = st.columns(2)

with upload_col1:
    orig_file = st.file_uploader(
        "📄 Original Presentation (.pptx)",
        type=["pptx", "ppt"],
        key="orig_uploader",
        help="Upload the original un-remediated presentation.",
    )

with upload_col2:
    rem_file = st.file_uploader(
        "✅ Remediated Presentation (.pptx)",
        type=["pptx", "ppt"],
        key="rem_uploader",
        help="Upload the remediated presentation to verify.",
    )

sample_col1, _ = st.columns([1, 4])
with sample_col1:
    use_sample = st.button("🧪 Load Sample Decks", help="Load built-in test decks covering missing content and shifted shapes")

# Session state setup
if "comparison_result" not in st.session_state:
    st.session_state.comparison_result = None
if "temp_workdir" not in st.session_state:
    st.session_state.temp_workdir = tempfile.mkdtemp(prefix="ppt_checker_")

workdir = Path(st.session_state.temp_workdir)

if use_sample:
    from tests.create_sample_decks import create_sample_decks
    sample_dir = workdir / "samples"
    sample_orig, sample_rem = create_sample_decks(sample_dir)
    st.session_state["sample_orig_path"] = str(sample_orig)
    st.session_state["sample_rem_path"] = str(sample_rem)
    st.success("Loaded sample presentations! Click 'Compare Presentations' below to run.")

active_orig_path: Optional[Path] = None
active_rem_path: Optional[Path] = None
orig_validation_error: Optional[str] = None
rem_validation_error: Optional[str] = None

if orig_file:
    active_orig_path = workdir / orig_file.name
    active_orig_path.write_bytes(orig_file.getvalue())
    try:
        validate_pptx_file(active_orig_path, file_label="Original file")
    except PresentationParseError as e:
        orig_validation_error = str(e)
        active_orig_path = None

if rem_file:
    active_rem_path = workdir / rem_file.name
    active_rem_path.write_bytes(rem_file.getvalue())
    try:
        validate_pptx_file(active_rem_path, file_label="Remediated file")
    except PresentationParseError as e:
        rem_validation_error = str(e)
        active_rem_path = None

if not orig_file and not rem_file and "sample_orig_path" in st.session_state and "sample_rem_path" in st.session_state:
    active_orig_path = Path(st.session_state["sample_orig_path"])
    active_rem_path = Path(st.session_state["sample_rem_path"])

if orig_validation_error:
    with upload_col1:
        st.error(f"⚠️ {orig_validation_error}")
if rem_validation_error:
    with upload_col2:
        st.error(f"⚠️ {rem_validation_error}")

# Font formatting toggle (persists in session state, default False)
st.markdown("<br/>", unsafe_allow_html=True)
check_fonts = st.checkbox(
    "Also check font formatting (font name, size, bold, italic, underline, color)",
    value=st.session_state.get("check_fonts", False),
    key="check_fonts",
    help="Turn on to detect font changes such as Arial to Times New Roman or bold removed.",
)

# Comparison Trigger
if active_orig_path and active_rem_path:
    start_btn = st.button("🚀 Compare Presentations", type="primary", use_container_width=True)

    if start_btn:
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        def update_progress(msg: str, pct: float):
            status_text.markdown(f"**{msg}**")
            progress_bar.progress(min(max(pct, 0.0), 1.0))

        try:
            validate_pptx_file(active_orig_path, file_label="Original file")
            validate_pptx_file(active_rem_path, file_label="Remediated file")

            with st.spinner("Analyzing presentations..."):
                res = compare_presentations(
                    orig_path=active_orig_path,
                    rem_path=active_rem_path,
                    enable_visual_preview=enable_preview,
                    text_threshold=float(text_threshold),
                    tolerance_emu=tolerance_emu,
                    check_fonts=check_fonts,
                    progress_callback=update_progress,
                    output_dir=workdir / "previews",
                )
                st.session_state.comparison_result = res
                st.session_state["active_orig_path"] = str(active_orig_path)
                st.session_state["active_rem_path"] = str(active_rem_path)
                st.session_state.pop("excel_report_bytes", None)
                st.session_state.pop("excel_preview_shots", None)
                st.success(f"Analysis completed in {res.processing_time_sec}s!")
        except PresentationParseError as e:
            st.error(f"⚠️ {e}")
        except Exception as e:
            st.error(f"⚠️ Error during comparison: {str(e)}")
        finally:
            status_text.empty()
            progress_bar.empty()

# -----------------------------------------------------------------------------
# Results Dashboard
# -----------------------------------------------------------------------------
settings_changed = False
if st.session_state.get("comparison_result") is not None:
    prev_check_fonts = getattr(st.session_state.comparison_result, "check_fonts", False)
    if prev_check_fonts != check_fonts:
        settings_changed = True
        st.warning("⚠️ Settings changed. Click Compare again to update results.")

result: Optional[DeckComparisonResult] = None if settings_changed else st.session_state.get("comparison_result")

if result:
    st.markdown("---")

    # Summary KPI Cards
    if result.check_fonts:
        m1, m2, m3, m4, m5 = st.columns(5)
    else:
        m1, m2, m4, m5 = st.columns(4)
        m3 = None

    with m1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-val" style="color: #F87171;">{result.rule1_errors_count}</div>
                <div class="metric-lbl">Rule 1: Content Errors</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-val" style="color: #FB923C;">{result.rule2_errors_count}</div>
                <div class="metric-lbl">Rule 2: Alignment Errors</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    if m3 is not None:
        with m3:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-val" style="color: #C084FC;">{result.font_errors_count}</div>
                    <div class="metric-lbl">Font Errors</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    with m4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-val" style="color: #4ADE80;">{result.pass_slides_count} / {len(result.slide_results)}</div>
                <div class="metric-lbl">Slides Passed</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m5:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-val" style="color: #F87171;">{result.fail_slides_count} / {len(result.slide_results)}</div>
                <div class="metric-lbl">Slides Failed</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -------------------------------------------------------------------------
    # Report Export & Downloads
    # -------------------------------------------------------------------------
    st.markdown("<br/>", unsafe_allow_html=True)
    st.subheader("📥 Export QA Reports")

    orig_file_for_report = st.session_state.get("active_orig_path")
    rem_file_for_report = st.session_state.get("active_rem_path")

    exp_col1, exp_col2 = st.columns([1.2, 1])

    with exp_col1:
        gen_clicked = st.button("📊 Generate Excel Report (with Embedded Problem Screenshots)", type="primary", use_container_width=True)
        if gen_clicked:
            prog_bar = st.progress(0.0)
            status_box = st.empty()
            try:
                status_box.info("Step 1/4: Rendering presentation slides to 150 DPI PNGs...")
                prog_bar.progress(0.15)

                shots_map = {}
                shots_dir = workdir / "excel_screenshots"
                shots_dir.mkdir(parents=True, exist_ok=True)

                if orig_file_for_report and rem_file_for_report:
                    try:
                        shots_map = generate_deck_highlighted_screenshots(
                            result=result,
                            orig_pptx_path=orig_file_for_report,
                            rem_pptx_path=rem_file_for_report,
                            output_dir=shots_dir,
                            progress_callback=lambda msg, p: (status_box.info(f"Step 2-3/4: {msg}"), prog_bar.progress(min(0.20 + 0.60 * p, 0.85))),
                        )
                        # Check if any slide had a render failure
                        failed_renders = [msg for msg in shots_map.values() if isinstance(msg, str) and msg.startswith("Render failed")]
                        if failed_renders:
                            for f_msg in failed_renders[:3]:
                                st.error(f"⚠️ {f_msg}")
                    except LibreOfficeNotFoundError:
                        st.error("⚠️ LibreOffice not found. Could not render slide screenshots.")
                    except Exception as err:
                        st.error(f"⚠️ Slide screenshot rendering encountered an issue: {str(err)}")

                status_box.info("Step 4/4: Building openpyxl Excel report with hyperlinks & embedding...")
                prog_bar.progress(0.90)

                excel_path = workdir / "PPT_Comparison_Report.xlsx"
                export_excel_report(result, excel_path, screenshots_map=shots_map)

                with open(excel_path, "rb") as f:
                    st.session_state["excel_report_bytes"] = f.read()

                valid_preview_shots = [p for p in shots_map.values() if isinstance(p, (str, Path)) and Path(str(p)).exists()]
                if valid_preview_shots:
                    st.session_state["excel_preview_shots"] = valid_preview_shots[:3]
                else:
                    st.session_state["excel_preview_shots"] = []

                prog_bar.progress(1.0)
                status_box.success("✓ Excel report built successfully with embedded highlighted problem screenshots!")
            except Exception as e:
                status_box.error(f"⚠️ Error creating Excel report: {str(e)}")

        if "excel_report_bytes" in st.session_state:
            st.download_button(
                "⬇️ Download PPT_Comparison_Report.xlsx",
                data=st.session_state["excel_report_bytes"],
                file_name="PPT_Comparison_Report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    with exp_col2:
        html_path = workdir / "comparison_report.html"
        export_html_report(result, html_path)
        with open(html_path, "rb") as f:
            st.download_button(
                "🌐 Download Standalone HTML Report",
                data=f.read(),
                file_name="PPT_Comparison_Report.html",
                mime="text/html",
                use_container_width=True,
            )

    # Preview of first 3 failing slide screenshots (if available)
    if st.session_state.get("excel_preview_shots"):
        st.markdown("<br/>", unsafe_allow_html=True)
        with st.expander("📸 Preview: Problem Area Screenshots (Embedded in Excel)", expanded=True):
            st.caption("Here is a preview of the problem area screenshots (30% dimming + padded boxes + corner numbers) embedded in the Excel report:")
            preview_cols = st.columns(len(st.session_state["excel_preview_shots"]))
            for p_idx, p_path in enumerate(st.session_state["excel_preview_shots"]):
                with preview_cols[p_idx]:
                    st.image(str(p_path), caption=f"Failing Slide Highlight Preview #{p_idx + 1}", use_container_width=True)

    # Deck-Level Issues (if any)
    if result.deck_issues:
        st.subheader("Deck-Level Content Issues")
        for d_iss in result.deck_issues:
            cls = "issue-card" if d_iss.is_error else "issue-card info"
            badge = "badge-error" if d_iss.is_error else "badge-info"
            st.markdown(
                f"""
                <div class="{cls}">
                    <div class="issue-top">
                        <span class="badge {badge}">{"Error" if d_iss.is_error else "Info"}</span>
                        <span class="issue-title">#{d_iss.issue_num} {d_iss.issue_type} - {d_iss.element_name}</span>
                    </div>
                    <div class="issue-desc">{d_iss.description}</div>
                    <div class="val-compare">
                        <div><span class="val-label">Original:</span> <span class="val-orig">{d_iss.original_value}</span></div>
                        <div><span class="val-label">Remediated:</span> <span class="val-rem">{d_iss.remediated_value}</span></div>
                        <div><span class="val-label">Difference:</span> <span class="val-diff">{d_iss.difference}</span></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # -------------------------------------------------------------------------
    # Filters & Slide View
    # -------------------------------------------------------------------------
    st.subheader("Slide-by-Slide Verification")

    f_col1, f_col2 = st.columns([1.5, 1.5])
    with f_col1:
        if result.check_fonts:
            slide_labels = [
                f"{s.slide_key} [{s.status.value}] (Content: {len(s.content_issues)}, Alignment: {len(s.alignment_issues)}, Font: {len(s.font_issues)})"
                for s in result.slide_results
            ]
        else:
            slide_labels = [
                f"{s.slide_key} [{s.status.value}] (Content: {len(s.content_issues)}, Alignment: {len(s.alignment_issues)})"
                for s in result.slide_results
            ]
        slide_filter = st.selectbox(
            "Select Slide:",
            ["All Slides"] + slide_labels
        )
    with f_col2:
        rule_choices = ["All Rules", "Content", "Alignment"] + (["Font"] if result.check_fonts else [])
        rule_filter = st.selectbox(
            "Filter by Rule:",
            rule_choices
        )

    # Determine which slide(s) to view
    if slide_filter == "All Slides":
        active_slide_res = result.slide_results[0] if result.slide_results else None
    else:
        sel_idx = slide_labels.index(slide_filter)
        active_slide_res = result.slide_results[sel_idx]

    if active_slide_res:
        stat_class = f"badge-{active_slide_res.status.value.lower()}"
        st.markdown(
            f"""
            <div style="background: #1E293B; border-radius: 8px; padding: 0.8rem 1.2rem; margin: 0.8rem 0; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 700; font-size: 1.1rem; color: #F8FAFC;">
                    {active_slide_res.slide_key}
                    <span style="font-size: 0.85rem; font-weight: normal; color: #94A3B8; margin-left: 0.5rem;">
                        (Original: Slide {active_slide_res.orig_index or 'None - Added'}, Remediated: Slide {active_slide_res.rem_index or 'None - Deleted'})
                    </span>
                </span>
                <span class="badge {stat_class}">{active_slide_res.status.value}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if result.check_fonts:
            tab1, tab2, tab3, tab4 = st.tabs([
                f"📋 Content Issues ({len(active_slide_res.content_issues)})",
                f"📐 Alignment Issues ({len(active_slide_res.alignment_issues)})",
                f"🔤 Font Issues ({len(active_slide_res.font_issues)})",
                "🖼️ Side-by-side Preview",
            ])
        else:
            tab1, tab2, tab4 = st.tabs([
                f"📋 Content Issues ({len(active_slide_res.content_issues)})",
                f"📐 Alignment Issues ({len(active_slide_res.alignment_issues)})",
                "🖼️ Side-by-side Preview",
            ])
            tab3 = None

        with tab1:
            if not active_slide_res.content_issues:
                st.success("✓ Content Preserved: All original text, images, charts, tables, notes, and links are fully preserved.")
            else:
                for iss in active_slide_res.content_issues:
                    cls = "issue-card" if iss.is_error else "issue-card info"
                    badge = "badge-error" if iss.is_error else "badge-info"
                    word_diff = render_word_level_diff(iss.original_value, iss.remediated_value)
                    diff_detail = f'<div><span class="val-label">Difference:</span> <span class="val-diff">{iss.difference}</span></div>'
                    if word_diff:
                        diff_detail += f'<div style="margin-top: 0.35rem;"><span class="val-label">Word-Level Text Diff:</span> <span>{word_diff}</span></div>'
                    st.markdown(
                        f"""
                        <div class="{cls}">
                            <div class="issue-top">
                                <span class="badge {badge}">{"Error" if iss.is_error else "Info"}</span>
                                <span class="issue-title">#{iss.issue_num} {iss.issue_type} - {iss.element_name}</span>
                            </div>
                            <div class="issue-desc">{iss.description}</div>
                            <div class="val-compare">
                                <div><span class="val-label">Original:</span> <span class="val-orig">{iss.original_value}</span></div>
                                <div><span class="val-label">Remediated:</span> <span class="val-rem">{iss.remediated_value}</span></div>
                                {diff_detail}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        with tab2:
            if not active_slide_res.alignment_issues:
                st.success("✓ Alignment Preserved: All elements are located at matching positions, sizes, and orientations.")
            else:
                for iss in active_slide_res.alignment_issues:
                    st.markdown(
                        f"""
                        <div class="issue-card">
                            <div class="issue-top">
                                <span class="badge badge-error">Alignment Error</span>
                                <span class="issue-title">#{iss.issue_num} {iss.issue_type} - {iss.element_name}</span>
                            </div>
                            <div class="issue-desc">{iss.description}</div>
                            <div class="val-compare">
                                <div><span class="val-label">Original:</span> <span class="val-orig">{iss.original_value}</span></div>
                                <div><span class="val-label">Remediated:</span> <span class="val-rem">{iss.remediated_value}</span></div>
                                <div><span class="val-label">Difference:</span> <span class="val-diff">{iss.difference}</span></div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        if tab3 is not None:
            with tab3:
                if not active_slide_res.font_issues:
                    st.success("✓ Font Preserved: All text elements retain original font typeface, size, and styling.")
                else:
                    for iss in active_slide_res.font_issues:
                        st.markdown(
                            f"""
                            <div class="issue-card">
                                <div class="issue-top">
                                    <span class="badge badge-error">Font Error</span>
                                    <span class="issue-title">#{iss.issue_num} {iss.issue_type} - {iss.element_name}</span>
                                </div>
                                <div class="issue-desc">{iss.description}</div>
                                <div class="val-compare">
                                    <div><span class="val-label">Original:</span> <span class="val-orig">{iss.original_value}</span></div>
                                    <div><span class="val-label">Remediated:</span> <span class="val-rem">{iss.remediated_value}</span></div>
                                    <div><span class="val-label">Difference:</span> <span class="val-diff">{iss.difference}</span></div>
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

        with tab4:
            if active_slide_res.orig_image_path or active_slide_res.rem_image_path:
                v_col1, v_col2 = st.columns(2)
                with v_col1:
                    st.caption(f"**Original Slide {active_slide_res.orig_index or ''}**")
                    if active_slide_res.orig_image_path and os.path.exists(active_slide_res.orig_image_path):
                        st.image(active_slide_res.orig_image_path, use_container_width=True)
                    else:
                        st.info("No original slide image available.")
                with v_col2:
                    st.caption(f"**Remediated Slide {active_slide_res.rem_index or ''}**")
                    if active_slide_res.rem_image_path and os.path.exists(active_slide_res.rem_image_path):
                        st.image(active_slide_res.rem_image_path, use_container_width=True)
                    else:
                        st.info("No remediated slide image available.")

                if active_slide_res.diff_image_path and os.path.exists(active_slide_res.diff_image_path):
                    st.markdown("---")
                    st.caption("**Visual Shift Highlight Overlay** (Positions/differences highlighted in magenta)")
                    st.image(active_slide_res.diff_image_path, use_container_width=True)
            else:
                st.info("Visual preview is disabled or LibreOffice is not available.")
else:
    st.info("👋 Upload both an Original and Remediated PowerPoint presentation above, or click 'Load Sample Decks' to run.")
