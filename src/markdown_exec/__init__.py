"""Markdown Exec package.

Utilities to execute code blocks in Markdown files.
"""

from markdown_exec._internal.blocks import ParsedBlock, SourceLocation
from markdown_exec._internal.formatters.base import (
    base_format,
    default_tabs,
)
from markdown_exec._internal.formatters.python import PythonRunner
from markdown_exec._internal.formatters.sh import ShellRunner
from markdown_exec._internal.logger import get_logger, patch_loggers
from markdown_exec._internal.main import MARKDOWN_EXEC_AUTO, custom_fences, formatter, formatters, validator
from markdown_exec._internal.renderer import BlockRenderer
from markdown_exec._internal.processors import (
    HeadingReportingTreeprocessor,
    IdPrependingTreeprocessor,
    InsertHeadings,
    RemoveHeadings,
)
from markdown_exec._internal.rendering import (
    MarkdownConfig,
    MarkdownConverter,
    add_source,
    code_block,
    markdown_config,
    tabbed,
)
from markdown_exec._internal.runner import (
    ExecutionError,
    ExecutionRequest,
    ExecutionResult,
    FunctionRunner,
    Runner,
    console_width,
    execute,
    working_directory,
)
from markdown_exec._internal.sessions import SessionManager, session_manager

__all__ = [
    "MARKDOWN_EXEC_AUTO",
    "BlockRenderer",
    "ExecutionError",
    "ExecutionRequest",
    "ExecutionResult",
    "FunctionRunner",
    "HeadingReportingTreeprocessor",
    "IdPrependingTreeprocessor",
    "InsertHeadings",
    "MarkdownConfig",
    "MarkdownConverter",
    "ParsedBlock",
    "PythonRunner",
    "RemoveHeadings",
    "Runner",
    "SessionManager",
    "ShellRunner",
    "SourceLocation",
    "add_source",
    "base_format",
    "code_block",
    "console_width",
    "custom_fences",
    "default_tabs",
    "execute",
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
