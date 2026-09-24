"""Tests for the parsed block / execution result / rendered insertion layers."""

from __future__ import annotations

import html as html_module
import re
import subprocess
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from functools import partial
from io import StringIO
from textwrap import dedent
from types import ModuleType
from typing import Any

import pytest
from markdown import Markdown

from markdown_exec import (
    ExecutionError,
    ExecutionRequest,
    ExecutionResult,
    MarkdownExecPlugin,
    PythonRunner,
    RecordingRenderer,
    RecordingRunner,
    Renderer,
    ShellRunner,
    base_format,
    code_block,
    custom_fences,
    session_manager,
)
from markdown_exec._internal.formatters._exec_python import exec_python


def _buffer_print(buffer: StringIO, *texts: str, end: str = "\n", **kwargs: Any) -> None:  # noqa: ARG001
    buffer.write(" ".join(str(text) for text in texts) + end)


def _legacy_run_python(
    code: str,
    returncode: int | None = None,  # noqa: ARG001
    session: str | None = None,
    id: str | None = None,  # noqa: A002
    **extra: str,
) -> str:
    """Reimplementation of the pre-refactor `_run_python` callable."""
    block_id = session_manager.block_id(identifier=id or "", session=session, title=extra.get("title"))
    session_manager.register_block(block_id, code)
    exec_globals = session_manager.globals_for(session)
    module_name = re.sub(r"[^a-zA-Z\d]+", "_", block_id)
    exec_globals["__name__"] = module_name
    sys.modules[module_name] = ModuleType(module_name)
    buffer = StringIO()
    exec_globals["print"] = partial(_buffer_print, buffer)
    try:
        exec_python(code, block_id, exec_globals)
    except Exception as error:
        trace = traceback.TracebackException.from_exception(error)
        for frame in trace.stack:
            if frame.filename.startswith("<code block: "):
                line = session_manager.source_line(frame.filename, frame.lineno)
                if sys.version_info >= (3, 13):
                    frame._lines = line  # ty:ignore[unresolved-attribute]
                else:
                    frame._line = line  # ty:ignore[unresolved-attribute]
        raise ExecutionError(code_block("python", "".join(trace.format()), **extra)) from error
    return buffer.getvalue()


def _legacy_run_sh(
    code: str,
    returncode: int | None = None,
    session: str | None = None,  # noqa: ARG001
    id: str | None = None,  # noqa: A002,ARG001
    **extra: str,
) -> str:
    """Reimplementation of the pre-refactor `_run_sh` callable."""
    process = subprocess.run(  # noqa: S603
        ["sh", "-c", code],  # noqa: S607
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        encoding="utf8",
    )
    if process.returncode != returncode:
        raise ExecutionError(code_block("sh", process.stdout, **extra), process.returncode)
    return process.stdout


def _normalize(text: str) -> str:
    """Normalize code block identifiers, which legitimately differ between runs."""
    text = re.sub(r"<code block: [^>]+>", "<BLOCK>", text)
    return re.sub(r"&lt;code block: [^&]+&gt;", "<BLOCK>", text)


def _text(html: str) -> str:
    """Strip HTML tags and unescape entities, to compare rendered text content."""
    return html_module.unescape(re.sub(r"<[^>]+>", "", str(html)))


_frame_re = re.compile(
    r'  File "(?!<code block:)[^"\n]*", line \d+, in [^\n]+\n(?:    [^\n]*\n)?(?:    [~^ ]*\n)?',
)


def _normalize_trace(text: str) -> str:
    """Normalize tracebacks: drop harness frames and code block identifiers.

    Frames outside `<code block: ...>` files legitimately differ between
    the legacy callable and the layered runner (they are the frames of
    whoever called `exec`), so they are excluded from the comparison.
    """
    return _frame_re.sub("", _normalize(text))


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records]


def test_execution_request_is_immutable() -> None:
    """Assert execution requests cannot be mutated by runners."""
    request = ExecutionRequest(code="x = 1", extra={"title": "hello"})
    with pytest.raises(FrozenInstanceError):
        request.code = "x = 2"  # type: ignore[misc]
    with pytest.raises(TypeError):
        request.extra["title"] = "changed"  # type: ignore[index]


def test_recording_runner_contract() -> None:
    """Assert runners turn immutable requests into full execution results."""
    recording = RecordingRunner(PythonRunner())
    request = ExecutionRequest(code="print('hi')", language="python")
    result = recording.run(request)
    assert result.ok
    assert result.stdout == "hi\n"
    assert result.stderr == ""
    assert result.returncode == 0
    assert result.artifacts == ()
    assert recording.records == [(request, result)]


def test_shell_runner_reports_exit_code() -> None:
    """Assert shell runners return stdout and exit codes without raising."""
    recording = RecordingRunner(ShellRunner("sh"))
    result = recording.run(ExecutionRequest(code="echo out\nexit 3", language="sh", returncode=0))
    assert not result.ok
    assert result.stdout == "out\n"
    assert result.returncode == 3
    assert result.error == "out\n"


def test_recording_renderer_contract(md: Markdown) -> None:
    """Assert renderers record both success and error rendering decisions."""
    renderer = RecordingRenderer(Renderer(md, language="python"))
    output = renderer.render_output("hello", "print('hello')")
    assert renderer.rendered_outputs == [("hello", "print('hello')")]
    assert "<p>hello</p>" in output
    error_result = ExecutionResult(error="boom", returncode=None)
    renderer.render_error(error_result)
    assert renderer.rendered_errors == [error_result]


def test_python_layered_matches_legacy(md: Markdown, caplog: pytest.LogCaptureFixture) -> None:
    """Assert the layered Python path renders the same HTML and warnings as before."""
    code = 'print("hello")\nraise ValueError("boom")'
    with caplog.at_level("WARNING"):
        legacy = base_format(language="python", run=_legacy_run_python, code=code, md=md)
    legacy_warnings = _warnings(caplog)
    caplog.clear()
    with caplog.at_level("WARNING"):
        layered = base_format(language="python", runner=PythonRunner(), code=code, md=md)
    layered_warnings = _warnings(caplog)
    assert _normalize_trace(_text(legacy)) == _normalize_trace(_text(layered))
    assert len(legacy_warnings) == len(layered_warnings) == 1
    assert [_normalize_trace(w) for w in legacy_warnings] == [_normalize_trace(w) for w in layered_warnings]


def test_python_success_layered_matches_legacy(md: Markdown) -> None:
    """Assert successful Python executions render identically in both paths."""
    code = "print('**hello**')"
    legacy = base_format(language="python", run=_legacy_run_python, code=code, md=md)
    layered = base_format(language="python", runner=PythonRunner(), code=code, md=md)
    assert legacy == layered == "<p><strong>hello</strong></p>"


def test_sh_layered_matches_legacy(md: Markdown, caplog: pytest.LogCaptureFixture) -> None:
    """Assert the layered shell path renders the same HTML and warnings as before."""
    code = "echo out\nexit 3"
    with caplog.at_level("WARNING"):
        legacy = base_format(language="sh", run=_legacy_run_sh, code=code, md=md)
    legacy_warnings = _warnings(caplog)
    caplog.clear()
    with caplog.at_level("WARNING"):
        layered = base_format(language="sh", runner=ShellRunner("sh"), code=code, md=md)
    layered_warnings = _warnings(caplog)
    assert legacy == layered
    assert legacy_warnings == layered_warnings
    assert "unexpected code 3" in layered_warnings[0]


def test_formatter_unexpected_exception_propagates(md: Markdown) -> None:
    """Assert unexpected formatter exceptions are not swallowed."""

    def explode(code: str, **_: Any) -> str:  # noqa: ARG001
        raise RuntimeError("formatter exploded")

    with pytest.raises(RuntimeError, match="formatter exploded"):
        base_format(language="python", run=explode, code="x = 1", md=md)


def test_formatter_execution_error_is_not_a_success(md: Markdown, caplog: pytest.LogCaptureFixture) -> None:
    """Assert a formatter raising `ExecutionError` renders an error, not a success."""

    def fail(code: str, **_: Any) -> str:  # noqa: ARG001
        raise ExecutionError("legacy failure payload")

    with caplog.at_level("WARNING"):
        html = base_format(language="python", run=fail, code="x = 1", md=md, source="tabbed-left")
    assert "legacy failure payload" in html
    assert "Source" not in html
    assert "exited with errors" in caplog.text


def test_runner_failure_is_not_rendered_as_success(md: Markdown, caplog: pytest.LogCaptureFixture) -> None:
    """Assert a failed execution result is never rendered as a successful one."""
    with caplog.at_level("WARNING"):
        html = base_format(
            language="python",
            runner=PythonRunner(),
            code="raise ValueError('boom')",
            md=md,
            source="tabbed-left",
        )
    assert "Traceback" in html
    assert "boom" in html
    assert "Source" not in html
    assert "exited with errors" in caplog.text


def test_session_close_drops_state(md: Markdown) -> None:
    """Assert closing a session drops its state."""
    md.convert('```python exec="1" session="closable"\nclosed_var = 1\n```')
    session_manager.close("closable")
    html = md.convert('```python exec="1" session="closable"\nprint(closed_var)\n```')
    assert "NameError" in html


def test_session_survives_without_close(md: Markdown) -> None:
    """Assert sessions keep their state until explicitly closed."""
    md.convert('```python exec="1" session="persistent"\nkept_var = 42\n```')
    html = md.convert('```python exec="1" session="persistent"\nprint(kept_var)\n```')
    assert "42" in html


def test_close_all_resets_sessions(md: Markdown) -> None:
    """Assert `close_all` drops every session."""
    md.convert('```python exec="1" session="wiped"\nwiped_var = 1\n```')
    session_manager.close_all()
    html = md.convert('```python exec="1" session="wiped"\nprint(wiped_var)\n```')
    assert "NameError" in html


def test_plugin_post_build_closes_sessions(md: Markdown) -> None:
    """Assert consecutive builds of the same plugin instance don't reuse sessions."""
    plugin = MarkdownExecPlugin()
    plugin.mkdocs_config_dir = None
    md.convert('```python exec="1" session="build-session"\nbuild_var = 1\n```')
    plugin.on_post_build(config=None)  # type: ignore[arg-type]
    html = md.convert('```python exec="1" session="build-session"\nprint(build_var)\n```')
    assert "NameError" in html


def test_two_files_same_block_index(md: Markdown) -> None:
    """Assert two files with the same block index get distinct, correct tracebacks."""
    html1 = md.convert('```python exec="1"\nraise ValueError("error from file one")\n```')
    html2 = md.convert('```python exec="1"\nraise ValueError("error from file two")\n```')
    assert "error from file one" in html1
    assert "error from file two" in html2
    ids1 = re.findall(r"&lt;code block: n(\d+)&gt;", html1)
    ids2 = re.findall(r"&lt;code block: n(\d+)&gt;", html2)
    assert ids1
    assert ids2
    assert set(ids1).isdisjoint(ids2)


def test_source_lines_point_to_original_fence(md: Markdown, caplog: pytest.LogCaptureFixture) -> None:
    """Assert traceback source lines are mapped back to the original fences."""
    with caplog.at_level("WARNING"):
        html = md.convert(
            dedent(
                """
                ```python exec="1" session="mapping"
                def fraise():
                    raise RuntimeError("strawberry")
                ```

                ```python exec="1" session="mapping"
                fraise()
                ```
                """,
            ),
        )
    # The raising line only exists in the first fence:
    # it can only show up in the second block's traceback through source mapping.
    assert 'raise RuntimeError("strawberry")' in caplog.text
    assert "fraise()" in caplog.text
    assert "strawberry" in html


def _convert_in_own_markdown(text: str) -> str:
    md = Markdown(
        extensions=["pymdownx.superfences"],
        extension_configs={"pymdownx.superfences": {"custom_fences": custom_fences(["python"])}},
    )
    return md.convert(text)


def test_parallel_builds() -> None:
    """Assert parallel builds produce correct, isolated output."""

    def build(index: int) -> str:
        return _convert_in_own_markdown(f'```python exec="1"\nprint("file {index}")\n```')

    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs = list(pool.map(build, range(8)))
    for index, output in enumerate(outputs):
        assert f"file {index}" in output


def test_parallel_builds_keep_source_mapping() -> None:
    """Assert parallel failing builds each map tracebacks to their own fence."""

    def build(index: int) -> str:
        return _convert_in_own_markdown(f'```python exec="1"\nraise ValueError("error {index}")\n```')

    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs = list(pool.map(build, range(8)))
    for index, output in enumerate(outputs):
        text = _text(output)
        assert f"error {index}" in text
        assert "raise ValueError(" in text


def test_hidden_lines_stay_hidden(md: Markdown) -> None:
    """Assert `markdown-exec: hide` lines are hidden from rendered sources."""
    html = md.convert(
        dedent(
            """
            ```python exec="1" source="above"
            print("hidden")  # markdown-exec: hide
            print("shown")
            ```
            """,
        ),
    )
    text = _text(html)
    assert "markdown-exec: hide" not in text
    # The hidden line only appears once: as program output, not as source.
    assert text.count("hidden") == 1
    assert "shown" in text


def test_working_directory_option(md: Markdown) -> None:
    """Assert the working directory option still applies to layered runners."""
    markup = base_format(language="sh", runner=ShellRunner("sh"), code="pwd", md=md, workdir="/")
    assert markup == "<p>/</p>"


def test_injected_print_and_imports(md: Markdown) -> None:
    """Assert injected `print` and module attributes still behave as before."""
    html = md.convert(
        dedent(
            """
            ```python exec="1"
            def func():
                pass

            print(f"`{func.__module__}`")
            ```
            """,
        ),
    )
    assert "_code_block_n" in html


def test_nested_markdown_output(md: Markdown) -> None:
    """Assert nested Markdown output is still rendered through the converter."""
    html = md.convert(
        dedent(
            """
            ```md exec="1"
            # Hello

            ```python
            print("not executed")
            ```
            ```
            """,
        ),
    )
    assert "Hello" in html
    assert "not executed" in html
