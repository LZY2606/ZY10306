from __future__ import annotations

import re
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from functools import partial
from io import StringIO
from types import MappingProxyType, ModuleType
from typing import TYPE_CHECKING, Any, Protocol

from markdown_exec._internal.formatters._exec_python import exec_python
from markdown_exec._internal.sessions import SessionManager, session_manager

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class ExecutionRequest:
    """Immutable request passed to runners.

    Runners must not mutate the request, and must not touch the Markdown
    tree: they only turn this request into an
    [`ExecutionResult`][markdown_exec.ExecutionResult].

    Attributes:
        code: The source code to execute.
        language: The code language, like python or bash.
        returncode: The expected exit code.
        session: An optional session name, to persist state between blocks.
        identifier: An optional user-provided identifier for the code block.
        extra: Extra, language-specific options (immutable mapping).
    """

    code: str
    language: str = ""
    returncode: int | None = 0
    session: str | None = None
    identifier: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "extra", MappingProxyType(dict(self.extra)))


@dataclass(frozen=True)
class ExecutionResult:
    """Result of executing code, before any rendering decision.

    Attributes:
        stdout: The captured standard output.
        stderr: The captured standard error (when not merged into stdout).
        returncode: The actual exit code (`None` when execution crashed).
        artifacts: Additional artifacts produced by the execution.
        error: The error payload to display, when execution failed.
        fenced_error: Whether the error payload is already fenced Markdown
            (legacy runners) or raw text the renderer must fence itself.
    """

    stdout: str = ""
    stderr: str = ""
    returncode: int | None = 0
    artifacts: tuple[Any, ...] = ()
    error: str | None = None
    fenced_error: bool = False

    @property
    def ok(self) -> bool:
        """Whether the execution succeeded."""
        return self.error is None


class Runner(Protocol):
    """Protocol for code runners.

    Runners receive an immutable [`ExecutionRequest`][markdown_exec.ExecutionRequest]
    and return an [`ExecutionResult`][markdown_exec.ExecutionResult].
    """

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Run the request and return its result.

        Parameters:
            request: The immutable execution request.

        Returns:
            The execution result.
        """
        ...  # pragma: no cover


class RecordingRunner:
    """Runner wrapper recording requests and results, for contract tests.

    Attributes:
        records: The recorded `(request, result)` pairs.
    """

    def __init__(self, runner: Runner) -> None:
        """Initialize the recording runner.

        Parameters:
            runner: The wrapped runner.
        """
        self.runner = runner
        self.records: list[tuple[ExecutionRequest, ExecutionResult]] = []

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Run the wrapped runner and record the exchange.

        Parameters:
            request: The immutable execution request.

        Returns:
            The execution result.
        """
        result = self.runner.run(request)
        self.records.append((request, result))
        return result


def _buffer_print(buffer: StringIO, *texts: str, end: str = "\n", **kwargs: Any) -> None:  # noqa: ARG001
    buffer.write(" ".join(str(text) for text in texts) + end)


class PythonRunner:
    """Runner executing Python code in-process, capturing printed output."""

    def __init__(self, sessions: SessionManager | None = None) -> None:
        """Initialize the Python runner.

        Parameters:
            sessions: The session manager owning execution state.
        """
        self.sessions = sessions if sessions is not None else session_manager

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute Python code and return the captured output.

        Parameters:
            request: The immutable execution request.

        Returns:
            The execution result.
        """
        code_block_id = self.sessions.block_id(
            identifier=request.identifier,
            session=request.session,
            title=request.extra.get("title"),
        )
        self.sessions.register_block(code_block_id, request.code)
        exec_globals = self.sessions.globals_for(request.session)

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
        except Exception as error:  # noqa: BLE001 (user code can raise anything)
            trace = traceback.TracebackException.from_exception(error)
            for frame in trace.stack:
                if frame.filename.startswith("<code block: "):
                    line = self.sessions.source_line(frame.filename, frame.lineno)
                    if sys.version_info >= (3, 13):
                        frame._lines = line  # ty:ignore[unresolved-attribute,unused-ignore-comment]
                    else:
                        frame._line = line  # ty:ignore[unresolved-attribute,unused-ignore-comment]
            return ExecutionResult(
                stdout=buffer.getvalue(),
                returncode=None,
                error="".join(trace.format()),
            )
        return ExecutionResult(stdout=buffer.getvalue(), returncode=0)


class ShellRunner:
    """Runner executing shell code in a subprocess."""

    def __init__(self, executable: str = "sh", encoding: str | None = "utf8") -> None:
        """Initialize the shell runner.

        Parameters:
            executable: The shell executable to run.
            encoding: The output encoding (`None` for the locale default).
        """
        self.executable = executable
        self.encoding = encoding

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute shell code and return the captured output.

        Parameters:
            request: The immutable execution request.

        Returns:
            The execution result.
        """
        process = subprocess.run(  # noqa: S603
            [self.executable, "-c", request.code],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            encoding=self.encoding,
        )
        if process.returncode != request.returncode:
            return ExecutionResult(stdout=process.stdout, returncode=process.returncode, error=process.stdout)
        return ExecutionResult(stdout=process.stdout, returncode=process.returncode)
