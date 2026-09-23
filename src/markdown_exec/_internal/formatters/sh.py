# Formatter for executing shell code.

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

from markdown_exec._internal.formatters.base import base_format
from markdown_exec._internal.runner import ExecutionResult

if TYPE_CHECKING:
    from markdown_exec._internal.runner import ExecutionRequest


class ShellRunner:
    """Run shell code blocks in a subprocess, capturing their output."""

    def __init__(self, executable: str = "sh") -> None:
        """Initialize the runner.

        Parameters:
            executable: The shell executable to run code with.
        """
        self._executable = executable

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Run shell code and return the captured output.

        Parameters:
            request: The immutable execution request.

        Returns:
            The execution result: captured output on success,
            or the failed process output in the error artifacts.
        """
        process = subprocess.run(  # noqa: S603
            [self._executable, "-c", request.code],  # noqa: S607
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            encoding="utf8",
        )
        ok = process.returncode == request.returncode
        return ExecutionResult(
            stdout=process.stdout if ok else "",
            returncode=process.returncode,
            ok=ok,
            error="" if ok else process.stdout,
            artifacts={} if ok else {"error_language": "sh"},
        )


def _format_sh(**kwargs: Any) -> str:
    return base_format(language="sh", runner=ShellRunner("sh"), **kwargs)
