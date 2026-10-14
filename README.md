# PPT Compare & QA Checker

A presentation comparison tool and web application built with Streamlit and Python to validate an **Original .pptx** against a **Remediated .pptx**, detecting regressions across **Content**, **Alignment / Layout**, and **Font** styling.

---

## QA Rules & Verification

### 1. Content Preservation
Every piece of content in the **Original** presentation must exist in the **Remediated** file. Checked per slide:
- **Light Normalization**: Both original and remediated text use a clean, safe normalization:
  - Any run of whitespace characters (spaces, tabs, newlines, carriage returns, NBSP `\u00A0`) is replaced with a single space, and leading/trailing spaces are trimmed.
  - Letter case and punctuation are preserved unchanged.
  - The full text of each shape is compared as one string, so differences in line breaks, paragraph splits, or run reformatting do not trigger false issues if the underlying words are the same (e.g., `"Concave down"` vs `"Concave  down"` produce zero issues).
  - Only real content differences (missing, changed, or extra words and characters) are reported (e.g., `"Concave down"` vs `"Concave dow"` is reported as Missing Text). The similarity threshold slider still applies.
- **Images, charts, tables, and shapes**: Must still exist. Compared by element type, count, and SHA-256 image blob hash.
- **Table structure**: Row and column counts must remain identical.
- **Speaker notes**: Notes text is preserved (using light whitespace normalization).
- **Hyperlinks**: Display text (normalized) and destination URL (leading/trailing trimmed) must match.
- **Slide count**: Flags missing or extra slides at the deck level.

*Reporting*: Missing content is flagged as an **Error** (causes slide failure); extra content only in remediated is flagged as an **Info** message. Remediation additions (alt text, slide titles, language, reading order, table headers) are ignored.

### 2. Alignment / Layout Preservation
Every element in the **Remediated** presentation must remain at the same position and orientation as in the **Original**.
- **Font Changes Never Cause False Alignment Errors**:
  - Rule 1 compares only text characters, never rendered spacing, line wraps, or text extents.
  - Rule 2 compares only shape box geometry stored directly in the file: `left`, `top`, `width`, `height`, rotation, paragraph alignment (`LEFT`, `CENTER`, `RIGHT`, `JUSTIFY`), and vertical anchor (`TOP`, `MIDDLE`, `BOTTOM`).
  - Never measures or infers positions from rendered slide images or text length/overflow.
  - Paragraph line spacing, character spacing, and autofit differences are ignored.
  - Resolves inherited positions from layout/master placeholders before comparing.
- **Shape Matching**: Shapes are matched between remediated and original slides using text similarity and position proximity.
- **Position & Dimensions**: Compares `left`, `top`, `width`, and `height` in EMU with configurable tolerance (default 0.05 inch = 45,720 EMU).
- **Rotation & Layout properties**:
  - Rotation angle (degrees, default 1.0° tolerance).
  - Text paragraph alignment (`LEFT`, `CENTER`, `RIGHT`, `JUSTIFY`), ignoring extra blank paragraphs.
  - Vertical anchor (`TOP`, `MIDDLE`, `BOTTOM`).
  - Z-order (stacking order in the slide shape tree).

*Reporting*: Each mismatch clearly reports the element name, original value, remediated value, and the difference.

### 3. Font Preservation (Optional & Strictly Separate)
Font comparison runs **only** when the optional *"Also check font formatting"* toggle is turned **ON** in the UI or `check_fonts=True` in the API:
- **When OFF (Default)**:
  - No font code runs and zero font issues can appear.
  - Slide evaluation is strictly based on Content and Alignment.
  - In Streamlit: Results display 4 KPI cards and 3 tabs (`Content Issues`, `Alignment Issues`, `Side-by-side Preview`).
  - In Excel & HTML reports: Summary notes *"Checks run: Content, Alignment"*, and Font rows/counts/screenshots are omitted.
- **When ON**:
  - Font differences are reported **ONLY** in the Font Issues tab and Font Issues report section, never as Content or Alignment issues.
  - Verifies typography across matched shapes:
    - **Font typeface / family** (e.g. `Arial` &rarr; `Times New Roman`).
    - **Font size** in points (tolerance 0.5 pt).
    - **Bold, italic, and underline** styling.
    - **Font color** (RGB/Hex).
    - Resolves inherited layout placeholder fonts.
  - In Streamlit: Displays the "Font Errors" KPI card and "🔤 Font Issues" tab.
  - In Excel: Summary notes *"Checks run: Content, Alignment, Font"* with full Font metrics and issue rows.

---

## Enhanced Excel Report with Embedded Problem Screenshots

For every slide with at least one issue, the exporter embeds a high-resolution side-by-side screenshot highlighting **only the problem area**:

1. **Slide Rendering & Caching**:
   - Headless LibreOffice (`soffice --headless --convert-to pdf`) converts both presentations to PDF once.
   - PyMuPDF (`fitz`) renders PNG slide images at **150 DPI**.
   - Renderings are cached per deck; only failing slides are processed.
2. **Problem Area Localization**:
   - Each issue carries shape bounding boxes in EMU (`left`, `top`, `width`, `height`).
   - EMU is mapped to pixels via:
     $$\text{pixel\_x} = \frac{\text{emu\_x}}{\text{slide\_width\_emu}} \times \text{image\_width\_px}$$
     $$\text{pixel\_y} = \frac{\text{emu\_y}}{\text{slide\_height\_emu}} \times \text{image\_height\_px}$$
   - Resolves inherited placeholder positions from slide layout/master when not overridden.
3. **Pillow Visual Highlighting**:
   - 30% dark overlay dims the rest of the slide, while problem areas retain 100% original brightness with **20 px padding**.
   - Bounding boxes are drawn with thick 3–4 px rectangles:
     - **Missing Content**: Red box on Original image.
     - **Alignment Shifts**: Green box on Original, Red box on Remediated.
     - **Font Issues**: Highlighted text box on both images.
   - Numbered badges (`#1`, `#2`...) at corner of problem area corresponding to the Excel issue number.
   - Combined side-by-side into a single image with "Original" and "Remediated" banners, resized to max 1200 px width to keep file sizes compact.
4. **openpyxl Workbook Structure**:
   - **`Summary`**: Total issues per rule (Content, Alignment, Font), per-slide Pass/Fail table.
   - **`Issues`**: Columns: `Issue #`, `Slide No`, `Rule` (color-coded), `Element Name`, `Description`, `Original Value`, `Remediated Value`, `Difference`, `Severity`, `Screenshot Ref`.
     - `Screenshot Ref` contains a clickable hyperlink (`#'Screenshots'!A{row}`) jumping directly to that slide's block.
     - Header styled with dark theme, freeze top row, and autofilter.
   - **`Screenshots`**: Slide blocks in sequential order with bold headings and embedded PNG images spaced to prevent overlapping.

---

## Streamlit Web UI

- **Friendly Validation**: Detects lock files (`~$`), files &le; 1 KB, legacy `.ppt` magic bytes (`D0 CF 11 E0`), and corrupt archives without tracebacks.
- **KPI Summary Cards**: Rule 1 Content Errors, Rule 2 Alignment Errors, Font Errors, Slides Passed, Slides Failed.
- **One-Click Excel Report Generator**: "Generate Excel Report (with Embedded Problem Screenshots)" button with real-time 4-step progress bar.
- **Instant Download**: `st.download_button` for `PPT_Comparison_Report.xlsx` cached in session state (avoids re-computation on click).
- **In-App Screenshots Preview**: Expander displays the first 3 failing slides' highlighted screenshots right inside the web interface.
- **Slide-by-Slide Verification**: Tabs for `Content Issues`, `Alignment Issues`, `Font Issues`, and `Side-by-side Preview`.

---

## Requirements & Setup

### 1. Prerequisites
- **Python 3.11+**
- **LibreOffice** (Installed and in `PATH` as `soffice`, or configured via `SOFFICE_PATH`)

### 2. Virtual Environment Setup
```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 3. LibreOffice Configuration
Windows LibreOffice paths are automatically detected (e.g. `C:\Program Files\LibreOffice\program\soffice.exe`). You can also specify:
```powershell
$env:SOFFICE_PATH = "C:\Program Files\LibreOffice\program\soffice.exe"
```

---

## Running the Application

Launch the Streamlit web app:
```powershell
.\.venv\Scripts\streamlit run app.py
```
Open your browser at `http://localhost:8501`.

Click **"🧪 Load Sample Decks"** in the sidebar to load the test presentations covering missing text, missing image, shifted shape, resized shape, and font changes.

---

## Running Tests

Run the full pytest suite:
```powershell
.\.venv\Scripts\python -m pytest -v
```

All 34 unit and integration test cases cover:
- EMU to pixel coordinate conversion and clamping
- Problem area dimming overlays and Pillow box highlighting
- openpyxl workbook export, screenshot image embedding, and sheet hyperlinks
- Rule 1 (Content), Rule 2 (Alignment), and Font preservation engines
- Slide matching, PPTX validation, and report exports
