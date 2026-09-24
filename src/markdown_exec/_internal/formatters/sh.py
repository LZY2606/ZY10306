# Formatter for executing shell code.

from __future__ import annotations

from typing import Any

from markdown_exec._internal.formatters.base import base_format
from markdown_exec._internal.runner import ShellRunner


def _format_sh(**kwargs: Any) -> str:
    return base_format(language="sh", runner=ShellRunner("sh"), **kwargs)
