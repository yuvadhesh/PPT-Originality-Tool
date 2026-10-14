from __future__ import annotations

import pytest
from pathlib import Path

from core.parser import (
    PresentationParseError,
    parse_presentation,
    validate_pptx_file,
)


def test_validate_valid_pptx(sample_decks):
    orig_path, _ = sample_decks
    # Should not raise any error
    validate_pptx_file(orig_path, file_label="Original file")


def test_validate_nonexistent_file(tmp_path):
    fake_path = tmp_path / "does_not_exist.pptx"
    with pytest.raises(PresentationParseError, match="Original file does not exist: does_not_exist.pptx"):
        validate_pptx_file(fake_path, file_label="Original file")


def test_validate_lock_file(tmp_path):
    lock_file = tmp_path / "~$presentation.pptx"
    lock_file.write_bytes(b"dummy lock data")
    with pytest.raises(
        PresentationParseError,
        match=r"Original file \('~\$presentation\.pptx'\): This is a temporary lock file, not the real presentation\."
    ):
        validate_pptx_file(lock_file, file_label="Original file")


def test_validate_empty_or_small_file(tmp_path):
    # 0 bytes
    empty_file = tmp_path / "empty.pptx"
    empty_file.write_bytes(b"")
    with pytest.raises(
        PresentationParseError,
        match=r"Remediated file \('empty\.pptx'\): File is empty or the upload was incomplete\."
    ):
        validate_pptx_file(empty_file, file_label="Remediated file")

    # Under 1 KB (e.g. 500 bytes)
    small_file = tmp_path / "partial.pptx"
    small_file.write_bytes(b"X" * 500)
    with pytest.raises(
        PresentationParseError,
        match=r"Original file \('partial\.pptx'\): File is empty or the upload was incomplete\."
    ):
        validate_pptx_file(small_file, file_label="Original file")


def test_validate_legacy_ppt_or_password_protected(tmp_path):
    # OLE2 Compound Document header: D0 CF 11 E0
    ppt_file = tmp_path / "legacy.ppt"
    ppt_file.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 2000)
    with pytest.raises(
        PresentationParseError,
        match=r"Original file \('legacy\.ppt'\): This is an old \.ppt or a password-protected file\. Please re-save as \.pptx\."
    ):
        validate_pptx_file(ppt_file, file_label="Original file")


def test_validate_corrupt_or_invalid_pptx(tmp_path):
    # Corrupt or not a valid PPTX (> 1KB)
    corrupt_file = tmp_path / "corrupt.pptx"
    corrupt_file.write_bytes(b"PK\x03\x04" + b"random_corrupt_data" * 100)
    with pytest.raises(
        PresentationParseError,
        match=r"Remediated file \('corrupt\.pptx'\): File is not a valid PPTX\. Please open it in PowerPoint and Save As \.pptx\."
    ):
        validate_pptx_file(corrupt_file, file_label="Remediated file")


def test_parse_presentation_structure(sample_decks):
    orig_path, rem_path = sample_decks

    meta_orig, slides_orig = parse_presentation(orig_path, file_label="Original file")
    assert meta_orig.slide_count == 7
    assert len(slides_orig) == 7
    assert slides_orig[0].title == "Introduction"

    meta_rem, slides_rem = parse_presentation(rem_path, file_label="Remediated file")
    assert meta_rem.slide_count == 7
    assert len(slides_rem) == 7
