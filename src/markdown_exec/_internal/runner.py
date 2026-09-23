# Execution layer: immutable requests in, execution results out.
#
# Runners receive an immutable execution request and return an immutable
# execution result (stdout, stderr, exit code and artifacts). They never
# touch the Markdown tree: rendering decisions are left to the renderer layer.

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Callable, Mapping, Protocol

from markdown_exec._internal.blocks import SourceLocation

if TYPE_CHECKING:
    from collections.abc import Iterator


class ExecutionError(Exception):
    """Exception raised for errors during execution of a code block.

    Attributes:
        message: The exception message.
        returncode: The code returned by the execution of the code block.
    """

    def __init__(self, message: str, returncode: int | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode
        """The code returned by the execution of the code block."""


@dataclass(frozen=True)
class ExecutionRequest:
    """An immutable request to execute code.

    Attributes:
        language: The code language, like python or bash.
        code: The code to execute (possibly transformed from the original fence).
        returncode: The expected exit code.
        session: A session name, to persist state between executed code blocks.
        id: An optional ID for the code block.
        extra: Additional options passed from the formatter.
        location: The location of the block in its source document, if known.
    """

    language: str
    """The code language, like python or bash."""

    code: str
    """The code to execute (possibly transformed from the original fence)."""

    returncode: int = 0
    """The expected exit code."""

    session: str | None = None
    """A session name, to persist state between executed code blocks."""

    id: str = ""
    """An optional ID for the code block."""

    extra: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    """Additional options passed from the formatter."""

    location: SourceLocation = field(default_factory=SourceLocation)
    """The location of the block in its source document, if known."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "extra", MappingProxyType(dict(self.extra)))


@dataclass(frozen=True)
class ExecutionResult:
    """An immutable result of executing code.

    Attributes:
        stdout: The captured standard output.
        stderr: The captured standard error.
        returncode: The exit code of the execution, if applicable.
        ok: Whether the execution succeeded. A failed execution is never
            marked as successful, even if it produced partial output.
        error: The error output to render when the execution failed.
        artifacts: Additional artifacts, such as the language to use
            when fencing the error output (`error_language`) or the
            identifier of the executed block (`block_id`).
    """

    stdout: str = ""
    """The captured standard output."""

    stderr: str = ""
    """The captured standard error."""

    returncode: int | None = None
    """The exit code of the execution, if applicable."""

    ok: bool = True
    """Whether the execution succeeded."""

    error: str = ""
    """The error output to render when the execution failed."""

    artifacts: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    """Additional artifacts produced by the execution."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifacts", MappingProxyType(dict(self.artifacts)))


class Runner(Protocol):
    """The runner contract: immutable request in, execution result out."""

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Run an execution request.

        Parameters:
            request: The immutable execution request.

        Returns:
            The execution result.
        """
        ...  # pragma: no cover


class FunctionRunner:
    """Adapt a legacy `run` callable (raising `ExecutionError`) to the runner contract."""

    def __init__(self, func: Callable) -> None:
        """Initialize the adapter.

        Parameters:
            func: A callable accepting code and keyword arguments,
                returning output and raising `ExecutionError` on failure.
        """
        self._func = func

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Run the wrapped callable with the given request.

        Parameters:
            request: The immutable execution request.

        Returns:
            The execution result.
        """
        try:
            output = self._func(
                request.code,
                returncode=request.returncode,
                session=request.session,
                id=request.id,
                **request.extra,
            )
        except ExecutionError as error:
            return ExecutionResult(ok=False, error=str(error), returncode=error.returncode)
        return ExecutionResult(stdout=output)


@contextmanager
def working_directory(path: str | None = None) -> Iterator[None]:
    """Change the working directory for the duration of the context.

    Parameters:
        path: The path to change the working directory to.
    """
    if path:
        old_cwd = Path.cwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(old_cwd)
    else:
        yield


@contextmanager
def console_width(width: int | None = None) -> Iterator[None]:
    """Set the console width for the duration of the context.

    The console width is set using the `COLUMNS` environment variable.

    Parameters:
        width: The width to set the console to.
    """
    if width:
        old_width = os.environ.get("COLUMNS", None)
        os.environ["COLUMNS"] = str(width)
        try:
            yield
        finally:
            if old_width is None:
                del os.environ["COLUMNS"]
            else:
                os.environ["COLUMNS"] = old_width
    else:
        yield


def execute(runner: Runner, request: ExecutionRequest, *, workdir: str | None = None, width: int | None = None) -> ExecutionResult:
    """Execute a request with the given runner, working directory and console width.

    Parameters:
        runner: The runner to execute the request with.
        request: The immutable execution request.
        workdir: The working directory to use for the execution.
        width: The console width to use for the execution.

    Returns:
        The execution result.
    """
    with working_directory(workdir), console_width(width):
        return runner.run(request)
