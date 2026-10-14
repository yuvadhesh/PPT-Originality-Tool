from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageOps
import pymupdf as fitz  # PyMuPDF
from skimage.metrics import structural_similarity


class LibreOfficeNotFoundError(Exception):
    """Raised when LibreOffice (soffice) executable is not found."""
    pass


import logging
logger = logging.getLogger(__name__)


def find_libreoffice_executable() -> str:
    """
    Find the LibreOffice soffice executable.
    Prioritizes:
    1. SOFFICE_PATH environment variable
    2. PATH environment variable ('soffice.com' / 'soffice')
    3. Common Windows installation locations (soffice.com preferred on Windows)
    """
    env_path = os.environ.get("SOFFICE_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    # On Windows, soffice.com is the console binary which waits properly for soffice.bin
    if os.name == "nt":
        which_com = shutil.which("soffice.com")
        if which_com:
            return which_com

    which_soffice = shutil.which("soffice")
    if which_soffice:
        return which_soffice

    # Windows fallback search paths
    default_windows_paths = [
        r"C:\Program Files\LibreOffice\program\soffice.com",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.com",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for p in default_windows_paths:
        if os.path.exists(p):
            return p

    raise LibreOfficeNotFoundError(
        "LibreOffice executable ('soffice') was not found in PATH or standard installation paths. "
        "Please ensure LibreOffice is installed and added to PATH, or set the SOFFICE_PATH environment variable."
    )


def convert_pptx_to_pdf(
    pptx_path: str | Path,
    output_dir: str | Path,
    user_installation_dir: Optional[str | Path] = None,
    timeout_sec: int = 180,
) -> Path:
    """
    Convert a PowerPoint presentation to PDF using LibreOffice in headless mode.
    Uses a unique user installation profile to prevent lock conflicts.
    """
    soffice_exe = find_libreoffice_executable()
    pptx_path = Path(pptx_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    temp_profile_to_cleanup: Optional[Path] = None
    if user_installation_dir:
        profile_path = Path(user_installation_dir).resolve()
        profile_path.mkdir(parents=True, exist_ok=True)
    else:
        temp_profile_to_cleanup = Path(tempfile.mkdtemp(prefix="lo_prof_")).resolve()
        profile_path = temp_profile_to_cleanup

    # Format file URL with forward slashes: file:///C:/path/to/profile
    profile_url = f"file:///{profile_path.as_posix().lstrip('/')}"

    cmd = [
        soffice_exe,
        f"-env:UserInstallation={profile_url}",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(pptx_path),
    ]

    logger.debug("[DEBUG] Running LibreOffice convert: cmd=%s", cmd)
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_sec,
            check=True,
        )
        logger.debug("[DEBUG] LibreOffice finished with exit code %s", res.returncode)
    except subprocess.TimeoutExpired as e:
        logger.error("[DEBUG] LibreOffice timed out after %ds converting %s", timeout_sec, pptx_path.name)
        raise RuntimeError(f"LibreOffice timed out after {timeout_sec}s converting {pptx_path.name}") from e
    except subprocess.CalledProcessError as e:
        logger.error("[DEBUG] LibreOffice conversion failed (exit %s): %s", e.returncode, e.stderr or e.stdout)
        raise RuntimeError(
            f"LibreOffice conversion failed (exit code {e.returncode}): {e.stderr or e.stdout}"
        ) from e
    finally:
        if temp_profile_to_cleanup and temp_profile_to_cleanup.exists():
            shutil.rmtree(temp_profile_to_cleanup, ignore_errors=True)

    expected_pdf = output_dir / f"{pptx_path.stem}.pdf"
    if not expected_pdf.exists():
        pdfs = list(output_dir.glob("*.pdf"))
        if pdfs:
            expected_pdf = pdfs[0]
        else:
            raise RuntimeError(f"Converted PDF file was not created in {output_dir}")

    pdf_size = expected_pdf.stat().st_size
    logger.debug("[DEBUG] Verified PDF exists: %s, size=%d bytes", expected_pdf, pdf_size)
    if pdf_size <= 0:
        raise RuntimeError(f"Converted PDF file is empty (0 bytes): {expected_pdf}")

    return expected_pdf


def render_pdf_to_images(
    pdf_path: str | Path,
    output_dir: str | Path,
    dpi: int = 150,
    prefix: str = "slide",
) -> List[Path]:
    """
    Render PDF pages to high-quality PNG images using PyMuPDF (fitz).
    Returns list of paths to slide images (1-indexed matching slide numbers).
    Verifies that rendered PNGs are non-blank.
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    image_paths: List[Path] = []

    # Calculate zoom scale for desired DPI (72 DPI default in PDF)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    for page_idx in range(len(doc)):
        page = doc.load_page(page_idx)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img_filename = f"{prefix}_{page_idx + 1:03d}.png"
        img_path = output_dir / img_filename
        pix.save(str(img_path))

        # Check for blank / solid color image
        with Image.open(img_path) as check_img:
            gray_im = check_img.convert("L")
            extrema = gray_im.getextrema()
            is_blank = (extrema[0] == extrema[1])
            if not is_blank:
                arr = np.array(gray_im)
                if np.std(arr) < 0.5:
                    is_blank = True

        if is_blank:
            doc.close()
            raise RuntimeError(
                f"Render failure: slide {page_idx + 1} PNG is blank/solid color (extrema={extrema})"
            )

        logger.debug("[DEBUG] Rendered page %d to %s", page_idx + 1, img_path)
        image_paths.append(img_path)

    doc.close()
    return image_paths


def render_deck_to_images(
    pptx_path: str | Path,
    expected_slide_count: Optional[int] = None,
    output_dir: Optional[str | Path] = None,
    dpi: int = 150,
    prefix: str = "slide",
    retries: int = 1,
) -> List[Path]:
    """
    Robustly render a presentation deck to 150 DPI PNG images:
    - Renders in a separate unique temp folder (tempfile.mkdtemp)
    - Copies input to '{prefix}.pptx'
    - Runs LibreOffice headless with unique UserInstallation profile
    - Verifies PDF exists, size > 0, and page count equals expected slide count
    - Renders pages to PNG with PyMuPDF, checking no image is blank
    - Retries once if conversion/rendering fails
    - Logs debug lines for every step (paths, sizes, page counts)
    """
    pptx_path = Path(pptx_path).resolve()
    if not pptx_path.exists():
        raise FileNotFoundError(f"Presentation file not found: {pptx_path}")

    last_error: Optional[Exception] = None

    for attempt in range(retries + 1):
        # Create separate unique temp folder for this conversion run
        unique_run_dir = Path(tempfile.mkdtemp(prefix=f"deck_render_{prefix}_")).resolve()
        copied_pptx = unique_run_dir / f"{prefix}.pptx"
        shutil.copy2(pptx_path, copied_pptx)
        logger.debug(
            "[DEBUG] Attempt %d: Copied '%s' (size=%d) to '%s'",
            attempt + 1,
            pptx_path,
            pptx_path.stat().st_size,
            copied_pptx,
        )

        try:
            pdf_path = convert_pptx_to_pdf(
                pptx_path=copied_pptx,
                output_dir=unique_run_dir / "pdf",
                timeout_sec=180,
            )

            # Verify page count with PyMuPDF
            doc = fitz.open(str(pdf_path))
            pdf_page_count = len(doc)
            doc.close()

            logger.debug(
                "[DEBUG] PDF page count = %d (expected=%s)",
                pdf_page_count,
                expected_slide_count,
            )

            if expected_slide_count is not None and expected_slide_count > 0:
                if pdf_page_count != expected_slide_count:
                    raise RuntimeError(
                        f"PDF page count ({pdf_page_count}) does not match expected slide count ({expected_slide_count})"
                    )

            target_img_dir = Path(output_dir).resolve() if output_dir else (unique_run_dir / "images")
            target_img_dir.mkdir(parents=True, exist_ok=True)

            images = render_pdf_to_images(
                pdf_path=pdf_path,
                output_dir=target_img_dir,
                dpi=dpi,
                prefix=prefix,
            )

            logger.debug(
                "[DEBUG] Successfully rendered %d slides for deck '%s' in %s",
                len(images),
                prefix,
                target_img_dir,
            )
            return images

        except Exception as e:
            last_error = e
            logger.warning(
                "[DEBUG] Attempt %d failed for '%s': %s",
                attempt + 1,
                prefix,
                str(e),
            )
            shutil.rmtree(unique_run_dir, ignore_errors=True)
            if attempt < retries:
                logger.info("[DEBUG] Retrying deck rendering for '%s'...", prefix)
                continue

    raise RuntimeError(
        f"Rendering failed for '{prefix}' deck after {retries + 1} attempts: {last_error}"
    ) from last_error


def compute_visual_diff(
    img_orig_path: str | Path,
    img_rem_path: str | Path,
    output_diff_path: str | Path,
) -> Tuple[float, Path]:
    """
    Compute SSIM score between two slide images and generate an annotated diff overlay image.
    Returns (ssim_score, output_diff_path).
    """
    img_orig = Image.open(img_orig_path).convert("RGB")
    img_rem = Image.open(img_rem_path).convert("RGB")

    # Match dimensions if they differ
    if img_orig.size != img_rem.size:
        target_size = (
            max(img_orig.width, img_rem.width),
            max(img_orig.height, img_rem.height),
        )
        img_orig = img_orig.resize(target_size, Image.Resampling.LANCZOS)
        img_rem = img_rem.resize(target_size, Image.Resampling.LANCZOS)

    # Convert to grayscale numpy arrays for SSIM
    gray_orig = np.array(img_orig.convert("L"))
    gray_rem = np.array(img_rem.convert("L"))

    # Calculate SSIM
    score, diff_map = structural_similarity(gray_orig, gray_rem, full=True)
    ssim_score = max(0.0, min(1.0, float(score)))

    # Diff map is in range [-1, 1], scale to [0, 255]
    # In diff_map, values close to 1.0 mean identical, lower values mean different
    diff_mask = ((1.0 - diff_map) * 127.5).astype(np.uint8)
    
    # Threshold mask to isolate actual differences (threshold at > 30 difference)
    binary_diff = diff_mask > 30

    # Build visual overlay:
    # 1. Remediated slide desaturated slightly for background context
    base_rem = np.array(img_rem)
    gray_base = np.array(img_rem.convert("L"))
    gray_3ch = np.stack([gray_base] * 3, axis=-1)
    blended_bg = (0.6 * base_rem + 0.4 * gray_3ch).astype(np.uint8)

    # 2. Highlight differing regions in vivid magenta/red
    highlight_color = np.array([235, 30, 80], dtype=np.uint8)  # Bright accessible magenta-red
    diff_overlay = blended_bg.copy()
    diff_overlay[binary_diff] = (
        0.35 * diff_overlay[binary_diff] + 0.65 * highlight_color
    ).astype(np.uint8)

    out_diff = Path(output_diff_path)
    out_diff.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(diff_overlay).save(str(out_diff))

    return round(ssim_score, 4), out_diff


def generate_deck_visual_diffs(
    orig_pptx: str | Path,
    rem_pptx: str | Path,
    output_dir: str | Path,
    slide_matches: List[Any],
    progress_callback=None,
) -> Dict[str, Dict[str, Any]]:
    """
    Render both presentations, compute SSIM and diff images for all slide pairs.
    Returns mapping: slide_key -> {ssim, orig_img, rem_img, diff_img, issues}
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results: Dict[str, Dict[str, Any]] = {}

    orig_render_dir = out_dir / "orig_slides"
    rem_render_dir = out_dir / "rem_slides"
    diff_render_dir = out_dir / "diff_slides"

    # Step 1: Convert original to PDF and images
    if progress_callback:
        progress_callback("Rendering original slides to images (150 DPI)...", 0.20)
    orig_images = render_deck_to_images(
        pptx_path=orig_pptx,
        output_dir=orig_render_dir,
        dpi=150,
        prefix="orig_slide",
    )

    # Step 2: Convert remediated to PDF and images
    if progress_callback:
        progress_callback("Rendering remediated slides to images (150 DPI)...", 0.50)
    rem_images = render_deck_to_images(
        pptx_path=rem_pptx,
        output_dir=rem_render_dir,
        dpi=150,
        prefix="rem_slide",
    )

    # Step 3: Compute SSIM and diffs for each match
    total_matches = len(slide_matches)
    for idx, match in enumerate(slide_matches):
        if progress_callback:
            pct = 0.60 + 0.35 * (idx / max(total_matches, 1))
            progress_callback(f"Analyzing visual diff for slide pair {idx + 1}/{total_matches}...", pct)

        orig_img_path = None
        rem_img_path = None
        diff_img_path = None
        ssim_score = None

        if match.orig_index and 1 <= match.orig_index <= len(orig_images):
            orig_img_path = str(orig_images[match.orig_index - 1])

        if match.rem_index and 1 <= match.rem_index <= len(rem_images):
            rem_img_path = str(rem_images[match.rem_index - 1])

        slide_key = f"rem_{match.rem_index}" if match.rem_index else f"orig_{match.orig_index}"

        # If both images exist, compute visual diff overlay
        if orig_img_path and rem_img_path:
            diff_file = diff_render_dir / f"diff_{slide_key}.png"
            ssim_score, diff_img_path_obj = compute_visual_diff(
                orig_img_path, rem_img_path, diff_file
            )
            diff_img_path = str(diff_img_path_obj)

        results[slide_key] = {
            "ssim": ssim_score,
            "orig_img": orig_img_path,
            "rem_img": rem_img_path,
            "diff_img": diff_img_path,
        }

    return results
