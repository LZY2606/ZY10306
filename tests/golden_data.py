"""Golden documents and normalization helpers for the recording contract tests.

The documents below are converted once with the pre-refactor implementation
(see `tests/fixtures/golden_outputs.json`) and replayed after the refactor to
assert identical HTML output and identical warning sequences.
"""

from __future__ import annotations

import html as html_module
import re
from pathlib import Path

import markdown_exec

PACKAGE_ROOT = Path(markdown_exec.__file__).resolve().parent
WORKSPACE_ROOT = PACKAGE_ROOT.parent.parent

DOCUMENTS: list[dict[str, str]] = [
    {
        "name": "python-markdown",
        "markdown": '```python exec="yes"\nprint("**Bold!**")\n```\n',
    },
    {
        "name": "python-html",
        "markdown": '```python exec="yes" html="yes"\nprint("**Bold!**")\n```\n',
    },
    {
        "name": "python-error",
        "markdown": '```python exec="yes"\nraise ValueError("oh no!")\n```\n',
    },
    {
        "name": "python-error-with-id",
        "markdown": '```python exec="yes" id="golden-block"\nbroken(\n```\n',
    },
    {
        "name": "python-sessions",
        "markdown": (
            '```python exec="1" session="golden"\n'
            "golden_value = 41\n"
            "```\n"
            "\n"
            '```python exec="1" session="golden"\n'
            "print(golden_value + 1)\n"
            "```\n"
        ),
    },
    {
        "name": "pycon-block",
        "markdown": '```pycon exec="1"\n>>> print("pycon ok")\n```\n',
    },
    {
        "name": "pycon-console-source",
        "markdown": '```pycon exec="1" source="console"\n>>> print("ok")\nko\n```\n',
    },
    {
        "name": "sh-markdown",
        "markdown": '```sh exec="yes"\necho "**Bold!**"\n```\n',
    },
    {
        "name": "sh-error",
        "markdown": '```sh exec="yes"\necho("wrong syntax")\n```\n',
    },
    {
        "name": "sh-returncode",
        "markdown": '```sh exec="yes" returncode="1"\necho Not in the mood\nexit 1\n```\n',
    },
    {
        "name": "bash-tabbed-source",
        "markdown": '```bash exec="1" source="tabbed-left"\necho hello\n```\n',
    },
    {
        "name": "console-block",
        "markdown": '```console exec="1"\n$ echo "console ok"\n```\n',
    },
    {
        "name": "md-nested",
        "markdown": '````md exec="1"\n```python exec="1"\nprint("**Bold!**")\n```\n````\n',
    },
    {
        "name": "python-source-and-result",
        "markdown": '```python exec="1" source="above" result="python"\nprint("hi")\n```\n',
    },
    {
        "name": "python-hidden-line",
        "markdown": (
            '```python exec="1" source="above"\n'
            'hidden = "x"  # markdown-exec: hide\n'
            "print(hidden)\n"
            "```\n"
        ),
    },
    {
        "name": "python-empty-output",
        "markdown": '```python exec="1"\nx = 1\n```\n',
    },
    {
        "name": "python-empty-output-with-source",
        "markdown": '```python exec="1" source="tabbed-left"\nx = 1\n```\n',
    },
    {
        "name": "python-error-with-source",
        "markdown": '```python exec="1" source="tabbed-left"\nraise RuntimeError("with source")\n```\n',
    },
]

_SPAN_RE = re.compile(r"</?span[^>]*>")
_PACKAGE_FRAME_RE = re.compile(r"(?m)^(?P<indent>[ ]*)File \"<ROOT>[^\n]*\n(?:(?P=indent)[ ]+[^\n]*\n?)*")


def normalize_text(text: str) -> str:
    """Normalize volatile parts of HTML output and log messages.

    - Unwrap Pygments `span` tags and unescape entities so highlighted
      code can be compared as plain text.
    - Replace the absolute workspace path with `<ROOT>`.
    - Drop traceback frames that point inside the markdown-exec package
      itself (their file names, line numbers and source lines depend on
      the implementation, which is exactly what the refactor changes).
      Frames pointing to `<code block: ...>` are kept: those are the
      source-mapped frames that must keep pointing back to the original
      fence.

    Parameters:
        text: The HTML output or log message to normalize.

    Returns:
        The normalized text.
    """
    text = _SPAN_RE.sub("", text)
    text = html_module.unescape(text)
    text = text.replace(str(WORKSPACE_ROOT), "<ROOT>")
    return _PACKAGE_FRAME_RE.sub("<PACKAGE FRAMES>\n", text)
