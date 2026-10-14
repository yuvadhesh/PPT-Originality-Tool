from __future__ import annotations

import pytest
from pathlib import Path

from tests.create_sample_decks import create_sample_decks


@pytest.fixture(scope="session")
def sample_decks(tmp_path_factory) -> tuple[Path, Path]:
    tmp_dir = tmp_path_factory.mktemp("decks")
    orig_path, rem_path = create_sample_decks(tmp_dir)
    return orig_path, rem_path
