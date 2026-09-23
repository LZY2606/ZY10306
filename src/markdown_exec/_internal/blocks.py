# Parsed code blocks: the first layer of the execution pipeline.
#
# A parsed block is an immutable description of a fenced code block
# and its execution/rendering options, as validated from the Markdown source.
# It does not know how to execute code nor how to render HTML:
# those are the responsibilities of the runner and renderer layers.

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class SourceLocation:
    """Location of a code block in its source document.

    Attributes:
        path: Path of the source document, if known.
        line: Line number of the opening fence in the source document (1-based), if known.
    """

    path: str | None = None
    """Path of the source document, if known."""

    line: int | None = None
    """Line number of the opening fence in the source document (1-based), if known."""

    def __str__(self) -> str:
        path = self.path or "<unknown>"
        if self.line is None:
            return path
        return f"{path}:{self.line}"


def _immutable_extra(extra: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    return MappingProxyType(dict(extra or {}))


@dataclass(frozen=True)
class ParsedBlock:
    """An immutable, parsed code block, ready to be executed and rendered.

    Attributes:
        language: The code language, like python or bash.
        code: The source code, as written in the original fence.
        id: An optional ID for the code block (useful when warning about errors).
        id_prefix: A string used to prefix HTML ids in the generated HTML.
        html: Whether to inject output as HTML directly, without rendering.
        source: Whether to show source as well, and where.
        result: If provided, use as language to format result in a code block.
        returncode: The expected exit code.
        session: A session name, to persist state between executed code blocks.
        update_toc: Whether to include generated headings in the Markdown table of contents.
        tabs: Titles of tabs (if used).
        workdir: The working directory to use for the execution.
        width: The console width to use for the execution.
        extra: Additional, language-agnostic options passed back to generated code blocks.
        location: The location of the block in its source document, if known.
    """

    language: str
    """The code language, like python or bash."""

    code: str
    """The source code, as written in the original fence."""

    id: str = ""
    """An optional ID for the code block (useful when warning about errors)."""

    id_prefix: str | None = None
    """A string used to prefix HTML ids in the generated HTML."""

    html: bool = False
    """Whether to inject output as HTML directly, without rendering."""

    source: str = ""
    """Whether to show source as well, and where."""

    result: str = ""
    """If provided, use as language to format result in a code block."""

    returncode: int = 0
    """The expected exit code."""

    session: str | None = None
    """A session name, to persist state between executed code blocks."""

    update_toc: bool = True
    """Whether to include generated headings in the Markdown table of contents."""

    tabs: tuple[str, str] = ("Source", "Result")
    """Titles of tabs (if used)."""

    workdir: str | None = None
    """The working directory to use for the execution."""

    width: int | None = None
    """The console width to use for the execution."""

    extra: Mapping[str, Any] = field(default_factory=_immutable_extra)
    """Additional options passed back to generated code blocks."""

    location: SourceLocation = field(default_factory=SourceLocation)
    """The location of the block in its source document, if known."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "extra", _immutable_extra(self.extra))
        if self.location is None:
            object.__setattr__(self, "location", SourceLocation())
