"""Configuration for the pytest test suite."""

import pytest
from markdown import Markdown

from markdown_exec import custom_fences, formatters


@pytest.fixture
def md() -> Markdown:
    """Return a Markdown instance.

    Returns:
        Markdown instance.
    """
    return Markdown(
        extensions=["pymdownx.superfences", "pymdownx.tabbed"],
        extension_configs={"pymdownx.superfences": {"custom_fences": custom_fences(list(formatters))}},
    )
