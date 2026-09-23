# Formatter for executing shell code.

from __future__ import annotations

from typing import Any

from markdown_exec._internal.formatters.base import base_format
from markdown_exec._internal.formatters.sh import ShellRunner


def _format_bash(**kwargs: Any) -> str:
    return base_format(language="bash", runner=ShellRunner("bash"), **kwargs)
