"""Markdown Exec package.

Utilities to execute code blocks in Markdown files.
"""

from markdown_exec._internal.formatters.base import (
    ExecutionError,
    base_format,
    console_width,
    default_tabs,
    working_directory,
)
from markdown_exec._internal.logger import get_logger, patch_loggers
from markdown_exec._internal.main import MARKDOWN_EXEC_AUTO, custom_fences, formatter, formatters, validator
from markdown_exec._internal.processors import (
    HeadingReportingTreeprocessor,
    IdPrependingTreeprocessor,
    InsertHeadings,
    RemoveHeadings,
)
from markdown_exec._internal.renderer import RecordingRenderer, Renderer
from markdown_exec._internal.rendering import (
    MarkdownConfig,
    MarkdownConverter,
    add_source,
    code_block,
    markdown_config,
    tabbed,
)
from markdown_exec._internal.runner import (
    ExecutionRequest,
    ExecutionResult,
    PythonRunner,
    RecordingRunner,
    Runner,
    ShellRunner,
)
from markdown_exec._internal.sessions import SessionManager, session_manager

__all__ = [
    "MARKDOWN_EXEC_AUTO",
    "ExecutionError",
    "ExecutionRequest",
    "ExecutionResult",
    "HeadingReportingTreeprocessor",
    "IdPrependingTreeprocessor",
    "InsertHeadings",
    "MarkdownConfig",
    "MarkdownConverter",
    "PythonRunner",
    "RecordingRenderer",
    "RecordingRunner",
    "RemoveHeadings",
    "Renderer",
    "Runner",
    "SessionManager",
    "ShellRunner",
    "add_source",
    "base_format",
    "code_block",
    "console_width",
    "custom_fences",
    "default_tabs",
    "formatter",
    "formatters",
    "get_logger",
    "markdown_config",
    "patch_loggers",
    "session_manager",
    "tabbed",
    "validator",
    "working_directory",
]


try:
    from markdown_exec._internal.mkdocs_plugin import MarkdownExecPlugin, MarkdownExecPluginConfig
except ImportError:
    pass
else:
    __all__ += [
        "MarkdownExecPlugin",
        "MarkdownExecPluginConfig",
    ]
