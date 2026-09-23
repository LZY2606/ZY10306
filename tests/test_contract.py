"""Recording contract tests: replay golden documents and compare HTML and warnings.

The golden outputs were recorded with the pre-refactor implementation
(see `tests/golden_data.py` for the normalization rules). Replaying the
same documents after the refactor must produce identical HTML output and
identical warning sequences.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from markdown import Markdown

from markdown_exec import MarkdownConverter, formatter, formatters, session_manager, validator
from tests import FIXTURES_DIR
from tests.golden_data import DOCUMENTS, normalize_text

if TYPE_CHECKING:
    import pytest


def _make_md() -> Markdown:
    fences = [{"name": language, "class": language, "validator": validator, "format": formatter} for language in formatters]
    return Markdown(
        extensions=["pymdownx.superfences", "pymdownx.tabbed"],
        extension_configs={"pymdownx.superfences": {"custom_fences": fences}},
    )


def test_golden_replay(caplog: pytest.LogCaptureFixture) -> None:
    """Assert HTML output and warning sequences are identical to the recorded baseline.

    Parameters:
        caplog: Pytest fixture to capture logs.
    """
    golden = json.loads((FIXTURES_DIR / "golden_outputs.json").read_text())
    assert {doc["name"] for doc in DOCUMENTS} == set(golden)

    # Reset all cross-build state so the replay matches the recording conditions.
    session_manager.close()
    MarkdownConverter.counter = 0

    with caplog.at_level(logging.WARNING):
        for doc in DOCUMENTS:
            caplog.clear()
            html = _make_md().convert(doc["markdown"])
            warnings = [
                [record.levelname, normalize_text(record.getMessage())]
                for record in caplog.records
                if record.levelno >= logging.WARNING
            ]
            expected = golden[doc["name"]]
            assert normalize_text(html) == expected["html"], doc["name"]
            assert warnings == expected["warnings"], doc["name"]
