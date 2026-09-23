# Generic formatter for executing code.
#
# This module wires the three layers of the execution pipeline together:
# it builds an immutable parsed block and execution request, runs the
# request through a runner, and renders the result with a block renderer.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from markupsafe import Markup

from markdown_exec._internal.blocks import ParsedBlock
from markdown_exec._internal.renderer import BlockRenderer
from markdown_exec._internal.runner import (
    ExecutionError,
    ExecutionRequest,
    FunctionRunner,
    Runner,
    console_width,
    execute,
    working_directory,
)

if TYPE_CHECKING:
    from markdown.core import Markdown

default_tabs = ("Source", "Result")
"""Default tab titles."""


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
        run: Function that runs code and returns output.
        runner: A runner accepting an immutable execution request
            and returning an execution result. Takes precedence over `run`.
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
    block = ParsedBlock(
        language=language,
        code=code,
        id=id,
        id_prefix=id_prefix,
        html=html,
        source=source,
        result=result,
        returncode=returncode,
        session=session,
        update_toc=update_toc,
        tabs=tabs,
        workdir=workdir,
        width=width,
        extra=extra,
    )

    if transform_source:
        source_input, source_output = transform_source(code)
    else:
        source_input = code
        source_output = code

    request = ExecutionRequest(
        language=language,
        code=source_input,
        returncode=returncode,
        session=session,
        id=id,
        extra=block.extra,
        location=block.location,
    )
    actual_runner: Runner = runner if runner is not None else FunctionRunner(run)  # type: ignore[arg-type]
    execution = execute(actual_runner, request, workdir=workdir, width=width)
    renderer = BlockRenderer(md, update_toc=update_toc)
    return renderer.render(block, request, execution, source_output=source_output)
