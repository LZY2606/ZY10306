# Formatter for executing Python code.

from __future__ import annotations

from typing import Any

from markdown_exec._internal.formatters.base import base_format
from markdown_exec._internal.runner import PythonRunner


def _format_python(**kwargs: Any) -> str:
    return base_format(language="python", runner=PythonRunner(), **kwargs)
