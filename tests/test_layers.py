"""Tests for the parsed block, execution and rendering layers."""

from __future__ import annotations

import logging
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from textwrap import dedent
import pytest
from markdown import Markdown

from tests.golden_data import normalize_text

from markdown_exec import (
    BlockRenderer,
    ExecutionError,
    ExecutionRequest,
    ExecutionResult,
    FunctionRunner,
    MarkdownConverter,
    ParsedBlock,
    SessionManager,
    SourceLocation,
    base_format,
    formatter,
    formatters,
    session_manager,
    validator,
)

def _make_md() -> Markdown:
    fences = [{"name": language, "class": language, "validator": validator, "format": formatter} for language in formatters]
    return Markdown(
        extensions=["pymdownx.superfences", "pymdownx.tabbed"],
        extension_configs={"pymdownx.superfences": {"custom_fences": fences}},
    )


class RecordingRunner:
    """A runner recording the requests it receives and playing back canned results."""

    def __init__(self, *results: ExecutionResult) -> None:
        self.requests: list[ExecutionRequest] = []
        """The received execution requests."""
        self._results = deque(results)

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Record the request and return the next canned result.

        Parameters:
            request: The immutable execution request.

        Returns:
            The next canned execution result.
        """
        self.requests.append(request)
        return self._results.popleft()


def test_execution_request_is_immutable() -> None:
    """Assert execution requests cannot be mutated."""
    request = ExecutionRequest(language="python", code="x = 1", extra={"title": "t"})
    with pytest.raises(FrozenInstanceError):
        request.code = "y = 2"  # type: ignore[misc]
    with pytest.raises(TypeError):
        request.extra["title"] = "u"  # type: ignore[index]


def test_execution_result_is_immutable() -> None:
    """Assert execution results cannot be mutated."""
    result = ExecutionResult(stdout="ok", artifacts={"block_id": "b"})
    with pytest.raises(FrozenInstanceError):
        result.ok = False  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.artifacts["block_id"] = "c"  # type: ignore[index]


def test_parsed_block_is_immutable() -> None:
    """Assert parsed blocks cannot be mutated."""
    block = ParsedBlock(language="python", code="x = 1")
    with pytest.raises(FrozenInstanceError):
        block.language = "sh"  # type: ignore[misc]
    with pytest.raises(TypeError):
        block.extra["title"] = "u"  # type: ignore[index]


def test_source_location_points_back_to_fence() -> None:
    """Assert source locations render as `path:line` of the original fence."""
    assert str(SourceLocation("docs/a.md", 12)) == "docs/a.md:12"
    assert str(SourceLocation("docs/a.md")) == "docs/a.md"
    assert str(SourceLocation()) == "<unknown>"


def test_recording_runner_contract(md: Markdown, caplog: pytest.LogCaptureFixture) -> None:
    """Assert the runner contract: immutable request in, execution result out.

    Parameters:
        md: A Markdown instance (fixture).
        caplog: Pytest fixture to capture logs.
    """
    runner = RecordingRunner(ExecutionResult(stdout="**ok**"))
    html = base_format(language="python", runner=runner, code="print('x')", md=md)
    assert html == "<p><strong>ok</strong></p>"
    (request,) = runner.requests
    assert isinstance(request, ExecutionRequest)
    assert request.language == "python"
    assert request.code == "print('x')"
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]


def test_renderer_decides_result_fence(md: Markdown) -> None:
    """Assert the renderer (not the runner) decides how results are fenced.

    Parameters:
        md: A Markdown instance (fixture).
    """
    runner = RecordingRunner(ExecutionResult(stdout="hello"))
    html = base_format(language="python", runner=runner, code="print('hi')", md=md, result="text")
    assert "<code>text" in html
    assert "hello" in html


def test_failed_result_is_never_marked_success(md: Markdown, caplog: pytest.LogCaptureFixture) -> None:
    """Assert partial output of a failed execution is discarded, not rendered as success.

    Parameters:
        md: A Markdown instance (fixture).
        caplog: Pytest fixture to capture logs.
    """
    result = ExecutionResult(
        stdout="partial output",
        ok=False,
        error="boom",
        returncode=2,
        artifacts={"error_language": "text"},
    )
    runner = RecordingRunner(result)
    html = base_format(language="python", runner=runner, code="print('x')", md=md)
    assert "boom" in html
    assert "partial output" not in html
    assert "exited with unexpected code 2" in caplog.text


def test_function_runner_adapts_legacy_callables() -> None:
    """Assert legacy `run` callables are adapted to the runner contract."""

    def legacy_run(code: str, returncode: int | None = None, **kwargs: str) -> str:
        if code == "fail":
            raise ExecutionError("legacy boom", 5)
        return f"output:{code}"

    runner = FunctionRunner(legacy_run)
    ok_result = runner.run(ExecutionRequest(language="python", code="hi", returncode=0))
    assert ok_result.ok
    assert ok_result.stdout == "output:hi"
    error_result = runner.run(ExecutionRequest(language="python", code="fail"))
    assert not error_result.ok
    assert error_result.error == "legacy boom"
    assert error_result.returncode == 5


def test_formatter_raising_execution_error(md: Markdown, caplog: pytest.LogCaptureFixture) -> None:
    """Assert a formatter raising `ExecutionError` renders the error and warns.

    Parameters:
        md: A Markdown instance (fixture).
        caplog: Pytest fixture to capture logs.
    """

    def raising(code: str, **kwargs: str) -> str:
        raise ExecutionError("kaboom", 7)

    html = base_format(language="python", run=raising, code="whatever", md=md)
    assert "kaboom" in html
    assert "exited with unexpected code 7" in caplog.text


def test_formatter_raising_unexpected_exception_propagates(md: Markdown) -> None:
    """Assert unexpected formatter exceptions propagate to the caller.

    Parameters:
        md: A Markdown instance (fixture).
    """

    def raising(code: str, **kwargs: str) -> str:
        raise RuntimeError("unexpected")

    with pytest.raises(RuntimeError, match="unexpected"):
        base_format(language="python", run=raising, code="whatever", md=md)


def test_session_manager_close_clears_state() -> None:
    """Assert closing a session manager drops globals, counters and recorded sources."""
    manager = SessionManager()
    block_id = manager.block_id(session="s")
    assert block_id == "<code block: session s; n1>"
    manager.globals_for("s")["x"] = 1
    manager.record_block(block_id, "line1\nline2")
    assert manager.source_line(block_id, 2) == "line2"

    manager.close()

    assert manager.globals_for("s") == {}
    assert manager.block_id(session="s") == block_id
    with pytest.raises(KeyError):
        manager.source_line(block_id, 1)


def test_session_manager_block_identifiers() -> None:
    """Assert block identifiers are unique and stable in format."""
    manager = SessionManager()
    assert manager.block_id() == "<code block: n1>"
    assert manager.block_id() == "<code block: n2>"
    assert manager.block_id(id="mine") == "<code block: id mine>"
    assert manager.block_id(session="s", title="t") == "<code block: session s; n1; title t>"


def test_consecutive_builds_do_not_reuse_sessions() -> None:
    """Assert closing the session manager between builds drops session state."""
    md_first = _make_md()
    md_first.convert('```python exec="1" session="builds"\nbuild_value = 1\n```\n')
    session_manager.close()
    MarkdownConverter.counter = 0
    md_second = _make_md()
    html = md_second.convert('```python exec="1" session="builds"\nprint(build_value)\n```\n')
    assert "NameError" in html
    session_manager.close()


def test_plugin_post_build_closes_sessions() -> None:
    """Assert the MkDocs plugin closes sessions on post-build, isolating consecutive builds."""
    mkdocs_plugin = pytest.importorskip("markdown_exec._internal.mkdocs_plugin")
    plugin = mkdocs_plugin.MarkdownExecPlugin()
    plugin.mkdocs_config_dir = None

    md_first = _make_md()
    md_first.convert('```python exec="1" session="plugin-builds"\nplugin_value = 1\n```\n')
    plugin.on_post_build(config=None)
    md_second = _make_md()
    html = md_second.convert('```python exec="1" session="plugin-builds"\nprint(plugin_value)\n```\n')
    assert "NameError" in html


def test_two_files_same_block_index(caplog: pytest.LogCaptureFixture) -> None:
    """Assert two files with a block at the same index keep their own source lines.

    Parameters:
        caplog: Pytest fixture to capture logs.
    """
    session_manager.close()
    file_a = _make_md()
    file_b = _make_md()
    with caplog.at_level(logging.WARNING):
        html_a = file_a.convert('```python exec="1"\nraise ValueError("error-from-file-a")\n```\n')
        html_b = file_b.convert('```python exec="1"\nraise ValueError("error-from-file-b")\n```\n')
    assert "error-from-file-a" in html_a
    assert "error-from-file-b" in html_b
    assert 'raise ValueError("error-from-file-a")' in caplog.text
    assert 'raise ValueError("error-from-file-b")' in caplog.text

    # A new build reuses the same block indices: recorded sources must not leak.
    session_manager.close()
    MarkdownConverter.counter = 0
    file_b2 = _make_md()
    with caplog.at_level(logging.WARNING):
        caplog.clear()
        html_b2 = file_b2.convert('```python exec="1"\nraise ValueError("error-from-second-build")\n```\n')
    assert "error-from-second-build" in html_b2
    assert 'raise ValueError("error-from-second-build")' in caplog.text
    assert 'raise ValueError("error-from-file-a")' not in caplog.text


def test_sessions_shared_across_files_within_a_build() -> None:
    """Assert sessions are shared across files of a single build."""
    session_manager.close()
    file_a = _make_md()
    file_b = _make_md()
    file_a.convert('```python exec="1" session="shared"\nshared_value = 5\n```\n')
    html = file_b.convert('```python exec="1" session="shared"\nprint(f"shared = {shared_value}")\n```\n')
    assert "shared = 5" in html
    session_manager.close()


def test_parallel_builds() -> None:
    """Assert parallel builds of independent documents do not interfere."""

    def build(index: int) -> str:
        md = _make_md()
        return md.convert(
            dedent(
                f"""
                ```python exec="1"
                print("value-{index}")
                ```

                ```python exec="1"
                raise ValueError("error-{index}")
                ```
                """,
            ),
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(build, range(8)))

    for index, html in enumerate(results):
        assert f"value-{index}" in html
        assert f"error-{index}" in html


def test_source_line_points_back_to_original_fence(md: Markdown) -> None:
    """Assert tracebacks show the source line as written in the original fence.

    Parameters:
        md: A Markdown instance (fixture).
    """
    html = md.convert(
        dedent(
            """
            ```python exec="1" source="above"
            hidden = "x"  # markdown-exec: hide
            raise ValueError("boom")
            ```
            """,
        ),
    )
    text = normalize_text(html)
    assert 'raise ValueError("boom")' in text
    assert "markdown-exec: hide" not in text


def test_warning_sequence_for_multiple_failures(md: Markdown, caplog: pytest.LogCaptureFixture) -> None:
    """Assert warnings are emitted in execution order, with the right identifiers.

    Parameters:
        md: A Markdown instance (fixture).
        caplog: Pytest fixture to capture logs.
    """
    with caplog.at_level(logging.WARNING):
        md.convert(
            dedent(
                """
                ```python exec="1" id="first"
                raise ValueError("one")
                ```

                ```sh exec="1"
                exit 3
                ```

                ```python exec="1" id="second"
                raise ValueError("two")
                ```
                """,
            ),
        )
    warnings = [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING]
    assert len(warnings) == 3
    assert "'first'" in warnings[0]
    assert "exited with errors" in warnings[0]
    assert "unexpected code 3" in warnings[1]
    assert "'second'" in warnings[2]
    assert "exited with errors" in warnings[2]


def test_renderer_includes_source_location_in_warnings(caplog: pytest.LogCaptureFixture) -> None:
    """Assert the renderer points warnings back to the original fence when known.

    Parameters:
        caplog: Pytest fixture to capture logs.
    """
    md = _make_md()
    block = ParsedBlock(
        language="python",
        code="raise ValueError('x')",
        id="located",
        location=SourceLocation("docs/a.md", 12),
    )
    request = ExecutionRequest(language="python", code=block.code, location=block.location)
    result = ExecutionResult(ok=False, error="boom")
    renderer = BlockRenderer(md)
    with caplog.at_level(logging.WARNING):
        renderer.render(block, request, result, source_output=block.code)
    assert "'located'" in caplog.text
    assert "at docs/a.md:12" in caplog.text
