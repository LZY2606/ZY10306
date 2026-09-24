from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from markupsafe import Markup

from markdown_exec._internal.rendering import MarkdownConverter, add_source, code_block

if TYPE_CHECKING:
    from markdown.core import Markdown

    from markdown_exec._internal.runner import ExecutionResult


class Renderer:
    """Turns execution results into rendered Markdown insertions.

    The renderer owns every presentation decision: fences, source
    insertion, result templates, id prefixes and error display policy.
    It never executes code itself.
    """

    def __init__(
        self,
        md: Markdown,
        *,
        language: str,
        html: bool = False,
        source: str = "",
        result: str = "",
        tabs: tuple[str, str] = ("Source", "Result"),
        identifier: str = "",
        id_prefix: str | None = None,
        update_toc: bool = True,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the renderer.

        Parameters:
            md: The Markdown instance.
            language: The code language.
            html: Whether to inject output as HTML directly, without rendering.
            source: Whether to show source as well, and where.
            result: If provided, use as language to format result in a code block.
            tabs: Titles of tabs (if used).
            identifier: An optional ID for the code block.
            id_prefix: A string used to prefix HTML ids in the generated HTML.
            update_toc: Whether to include generated headings
                into the Markdown table of contents (toc extension).
            extra: Extra options added back to generated code blocks.
        """
        self.language = language
        self.html = html
        self.source = source
        self.result = result
        self.tabs = tabs
        self.identifier = identifier
        self.id_prefix = id_prefix
        self.extra = extra or {}
        self.markdown = MarkdownConverter(md, update_toc=update_toc)

    @property
    def _error_language(self) -> str:
        return {"bash": "sh"}.get(self.language, self.language)

    def render_error(self, result: ExecutionResult) -> Markup:
        """Render a failed execution result, without marking it as successful.

        Parameters:
            result: The failed execution result.

        Returns:
            Safe HTML.
        """
        error = result.error or ""
        payload = error if result.fenced_error else code_block(self._error_language, error, **self.extra)
        return self.markdown.convert(payload)

    def render_output(self, output: str, source_output: str) -> Markup:
        """Render a successful execution result, optionally with its source.

        Parameters:
            output: The execution output.
            source_output: The source code to display (if the source option is enabled).

        Returns:
            Safe HTML.
        """
        if self.html:
            if self.source:
                placeholder = f'<div class="{uuid4()}"></div>'
                wrapped_output = add_source(
                    source=source_output,
                    location=self.source,
                    output=placeholder,
                    language=self.language,
                    tabs=self.tabs,
                    **self.extra,
                )
                return self.markdown.convert(wrapped_output, stash={placeholder: output})
            return Markup(output)  # noqa: S704

        wrapped_output = output
        if self.result and self.source != "console":
            wrapped_output = code_block(self.result, output)
        if self.source:
            wrapped_output = add_source(
                source=source_output,
                location=self.source,
                output=wrapped_output,
                language=self.language,
                tabs=self.tabs,
                result=self.result,
                **self.extra,
            )
        prefix = self.id_prefix if self.id_prefix is not None else (f"{self.identifier}-" if self.identifier else None)
        return self.markdown.convert(wrapped_output, id_prefix=prefix)


class RecordingRenderer:
    """Renderer wrapper recording rendering decisions, for contract tests.

    Attributes:
        rendered_outputs: The recorded `(output, source_output)` pairs.
        rendered_errors: The recorded failed execution results.
    """

    def __init__(self, renderer: Renderer) -> None:
        """Initialize the recording renderer.

        Parameters:
            renderer: The wrapped renderer.
        """
        self.renderer = renderer
        self.rendered_outputs: list[tuple[str, str]] = []
        self.rendered_errors: list[ExecutionResult] = []

    def render_output(self, output: str, source_output: str) -> Markup:
        """Record and render a successful output.

        Parameters:
            output: The execution output.
            source_output: The source code to display.

        Returns:
            Safe HTML.
        """
        self.rendered_outputs.append((output, source_output))
        return self.renderer.render_output(output, source_output)

    def render_error(self, result: ExecutionResult) -> Markup:
        """Record and render a failed execution result.

        Parameters:
            result: The failed execution result.

        Returns:
            Safe HTML.
        """
        self.rendered_errors.append(result)
        return self.renderer.render_error(result)
