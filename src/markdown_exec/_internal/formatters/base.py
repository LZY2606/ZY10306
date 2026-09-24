# Generic formatter for executing code.

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from textwrap import indent
from typing import TYPE_CHECKING, Any

from markupsafe import Markup

from markdown_exec._internal.logger import get_logger
from markdown_exec._internal.renderer import Renderer
from markdown_exec._internal.runner import ExecutionRequest, ExecutionResult

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from markdown.core import Markdown

    from markdown_exec._internal.runner import Runner

_logger = get_logger(__name__)

default_tabs = ("Source", "Result")
"""Default tab titles."""


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


def _format_log_details(details: str, *, strip_fences: bool = False) -> str:
    if strip_fences:
        lines = details.split("\n")
        if lines[0].startswith("```") and lines[-1].startswith("```"):
            details = "\n".join(lines[1:-1])
    return indent(details, " " * 2)


class _CallableRunner:
    """Adapter turning a legacy `run` callable into a runner."""

    def __init__(self, func: Callable) -> None:
        self.func = func

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        try:
            output = self.func(
                request.code,
                returncode=request.returncode,
                session=request.session,
                id=request.identifier,
                **request.extra,
            )
        except ExecutionError as error:
            return ExecutionResult(error=str(error), returncode=error.returncode, fenced_error=True)
        return ExecutionResult(stdout=output, returncode=request.returncode)


def base_format(
    *,
    language: str,
    run: Callable | None = None,
    runner: Runner | None = None,
    code: str,
    md: Markdown,
    html: bool = False,
    source: str = "",
    result: str = "",
    tabs: tuple[str, str] = default_tabs,
    id: str = "",  # noqa: A002
    id_prefix: str | None = None,
    returncode: int = 0,
    transform_source: Callable[[str], tuple[str, str]] | None = None,
    session: str | None = None,
    update_toc: bool = True,
    workdir: str | None = None,
    width: int | None = None,
    **options: Any,
) -> Markup:
    """Execute code and return HTML.

    Parameters:
        language: The code language.
        run: Function that runs code and returns output (legacy interface,
            adapted into a runner).
        runner: A runner turning an immutable execution request
            into an execution result.
        code: The code to execute.
        md: The Markdown instance.
        html: Whether to inject output as HTML directly, without rendering.
        source: Whether to show source as well, and where.
        result: If provided, use as language to format result in a code block.
        tabs: Titles of tabs (if used).
        id: An optional ID for the code block (useful when warning about errors).
        id_prefix: A string used to prefix HTML ids in the generated HTML.
        returncode: The expected exit code.
        transform_source: An optional callable that returns transformed versions of the source.
            The input source is the one that is ran, the output source is the one that is
            rendered (when the source option is enabled).
        session: A session name, to persist state between executed code blocks.
        update_toc: Whether to include generated headings
            into the Markdown table of contents (toc extension).
        workdir: The working directory to use for the execution.
        **options: Additional options passed from the formatter.

    Returns:
        HTML contents.
    """
    extra = options.get("extra", {})

    if transform_source:
        source_input, source_output = transform_source(code)
    else:
        source_input = code
        source_output = code

    if runner is None:
        runner = _CallableRunner(run)
    renderer = Renderer(
        md,
        language=language,
        html=html,
        source=source,
        result=result,
        tabs=tabs,
        identifier=id,
        id_prefix=id_prefix,
        update_toc=update_toc,
        extra=extra,
    )
    request = ExecutionRequest(
        code=source_input,
        language=language,
        returncode=returncode,
        session=session,
        identifier=id,
        extra=extra,
    )
    with working_directory(workdir), console_width(width):
        execution = runner.run(request)

    if not execution.ok:
        identifier = id or extra.get("title", "")
        identifier = identifier and f"'{identifier}' "
        exit_message = "errors" if execution.returncode is None else f"unexpected code {execution.returncode}"
        log_message = (
            f"Execution of {language} code block {identifier}exited with {exit_message}\n\n"
            f"Code block is:\n\n{_format_log_details(source_input)}\n\n"
            f"Output is:\n\n{_format_log_details(execution.error or '', strip_fences=True)}\n"
        )
        _logger.warning(log_message)
        return renderer.render_error(execution)

    output = execution.stdout
    if not output and not source:
        return Markup()

    return renderer.render_output(output, source_output)
