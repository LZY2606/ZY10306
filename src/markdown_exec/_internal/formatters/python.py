# Formatter for executing Python code.

from __future__ import annotations

import re
import sys
import traceback
from functools import partial
from io import StringIO
from types import ModuleType
from typing import TYPE_CHECKING, Any

from markdown_exec._internal.formatters._exec_python import exec_python
from markdown_exec._internal.formatters.base import base_format
from markdown_exec._internal.runner import ExecutionResult
from markdown_exec._internal.sessions import SessionManager, session_manager

if TYPE_CHECKING:
    from markdown_exec._internal.runner import ExecutionRequest


def _buffer_print(buffer: StringIO, *texts: str, end: str = "\n", **kwargs: Any) -> None:  # noqa: ARG001
    buffer.write(" ".join(str(text) for text in texts) + end)


class PythonRunner:
    """Run Python code blocks, capturing printed output and tracebacks."""

    def __init__(self, sessions: SessionManager | None = None) -> None:
        """Initialize the runner.

        Parameters:
            sessions: The session manager owning persistent state.
                Defaults to the shared session manager.
        """
        self._sessions = sessions if sessions is not None else session_manager

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Run Python code and return the captured output.

        Parameters:
            request: The immutable execution request.

        Returns:
            The execution result: captured output on success,
            a source-mapped traceback in the error artifacts on failure.
        """
        session = request.session or None
        title = request.extra.get("title")
        code_block_id = self._sessions.block_id(request.id or None, session, title)
        self._sessions.record_block(code_block_id, request.code)
        exec_globals = self._sessions.globals_for(session)

        # Other libraries expect functions to have a valid `__module__` attribute.
        # To achieve this, we need to add a `__name__` attribute to the globals.
        # We compute the name from the code block ID, replacing invalid characters with `_`.
        # We also create a module object with the same name and add it to `sys.modules`,
        # because that's what yet other libraries expect (`dataclasses` for example).
        module_name = re.sub(r"[^a-zA-Z\d]+", "_", code_block_id)
        exec_globals["__name__"] = module_name
        sys.modules[module_name] = ModuleType(module_name)

        buffer = StringIO()
        exec_globals["print"] = partial(_buffer_print, buffer)

        try:
            exec_python(request.code, code_block_id, exec_globals)
        except Exception as error:
            trace = traceback.TracebackException.from_exception(error)
            for frame in trace.stack:
                if frame.filename.startswith("<code block: "):
                    source_line = self._sessions.source_line(frame.filename, frame.lineno)
                    if sys.version_info >= (3, 13):
                        frame._lines = source_line  # ty:ignore[unresolved-attribute,unsupported-operator,unused-ignore-comment,unused-ignore-comment]
                    else:
                        frame._line = source_line  # ty:ignore[unresolved-attribute,unsupported-operator,unused-ignore-comment,unused-ignore-comment]
            return ExecutionResult(
                ok=False,
                error="".join(trace.format()),
                artifacts={"error_language": "python", "block_id": code_block_id},
            )
        return ExecutionResult(stdout=buffer.getvalue())


def _format_python(**kwargs: Any) -> str:
    return base_format(language="python", runner=PythonRunner(), **kwargs)
