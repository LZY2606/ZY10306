# Rendering layer: execution results in, rendered insertions out.
#
# The renderer decides how executed blocks are inserted back into the
# Markdown tree: fencing of results, source display, result templates,
# id prefixes and error display policy. It never executes code itself.

from __future__ import annotations

from textwrap import indent
from typing import TYPE_CHECKING
from uuid import uuid4

from markupsafe import Markup

from markdown_exec._internal.logger import get_logger
from markdown_exec._internal.rendering import MarkdownConverter, add_source, code_block

if TYPE_CHECKING:
    from markdown.core import Markdown

    from markdown_exec._internal.blocks import ParsedBlock
    from markdown_exec._internal.runner import ExecutionRequest, ExecutionResult

_logger = get_logger(__name__)


def _format_log_details(details: str, *, strip_fences: bool = False) -> str:
    if strip_fences:
        lines = details.split("\n")
        if lines[0].startswith("```") and lines[-1].startswith("```"):
            details = "\n".join(lines[1:-1])
    return indent(details, " " * 2)


class BlockRenderer:
    """Render parsed blocks and their execution results as HTML insertions."""

    def __init__(self, md: Markdown, *, update_toc: bool = True) -> None:
        """Initialize the renderer.

        Parameters:
            md: The Markdown instance to render output with.
            update_toc: Whether to include generated headings
                into the Markdown table of contents (toc extension).
        """
        self._markdown = MarkdownConverter(md, update_toc=update_toc)

    def render(
        self,
        block: ParsedBlock,
        request: ExecutionRequest,
        result: ExecutionResult,
        *,
        source_output: str,
    ) -> Markup:
        """Render an executed block as safe HTML.

        Parameters:
            block: The parsed code block.
            request: The execution request that was sent to the runner.
            result: The execution result returned by the runner.
            source_output: The source to render when the `source` option is enabled.

        Returns:
            HTML contents.
        """
        if not result.ok:
            return self.render_error(block, request, result)

        output = result.stdout
        if not output and not block.source:
            return Markup()

        extra = dict(block.extra)
        if block.html:
            if block.source:
                placeholder = f'<div class="{uuid4()}"></div>'
                wrapped_output = add_source(
                    source=source_output,
                    location=block.source,
                    output=placeholder,
                    language=block.language,
                    tabs=block.tabs,
                    **extra,
                )
                return self._markdown.convert(wrapped_output, stash={placeholder: output})
            return Markup(output)  # noqa: S704

        wrapped_output = output
        if block.result and block.source != "console":
            wrapped_output = code_block(block.result, output)
        if block.source:
            wrapped_output = add_source(
                source=source_output,
                location=block.source,
                output=wrapped_output,
                language=block.language,
                tabs=block.tabs,
                result=block.result,
                **extra,
            )
        prefix = block.id_prefix if block.id_prefix is not None else (f"{block.id}-" if block.id else None)
        return self._markdown.convert(wrapped_output, id_prefix=prefix)

    def render_error(self, block: ParsedBlock, request: ExecutionRequest, result: ExecutionResult) -> Markup:
        """Render a failed execution, following the error display policy.

        A failed execution is never marked as successful: partial output
        is discarded and the error output is rendered instead, while a
        warning is emitted with the block identifier and source location.

        Parameters:
            block: The parsed code block.
            request: The execution request that was sent to the runner.
            result: The failed execution result.

        Returns:
            HTML contents.
        """
        identifier = block.id or block.extra.get("title", "")
        identifier = identifier and f"'{identifier}' "
        exit_message = "errors" if result.returncode is None else f"unexpected code {result.returncode}"
        location = f" (at {block.location})" if block.location.line is not None else ""
        error_output = result.error
        error_language = result.artifacts.get("error_language")
        if error_language:
            error_output = code_block(error_language, error_output, **block.extra)
        log_message = (
            f"Execution of {block.language} code block {identifier}{location}exited with {exit_message}\n\n"
            f"Code block is:\n\n{_format_log_details(request.code)}\n\n"
            f"Output is:\n\n{_format_log_details(error_output, strip_fences=True)}\n"
        )
        _logger.warning(log_message)
        return self._markdown.convert(error_output)
