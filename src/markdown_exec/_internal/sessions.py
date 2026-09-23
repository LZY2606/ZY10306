# Session state for executed code blocks.
#
# The session manager explicitly owns all the state that persists
# across executed code blocks: session globals, block counters and
# the source lines of executed blocks (used to map tracebacks back
# to the original fences). Closing the manager drops all state,
# so that consecutive builds never reuse stale sessions.

from __future__ import annotations

import threading
from collections import defaultdict


class SessionManager:
    """Own the state shared by executed code blocks, with explicit close semantics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._globals: dict[str, dict] = defaultdict(dict)
        self._counter: dict[str | None, int] = defaultdict(int)
        self._code_blocks: dict[str, list[str]] = {}

    def block_id(self, id: str | None = None, session: str | None = None, title: str | None = None) -> str:  # noqa: A002
        """Compute the unique identifier of an executed code block.

        Parameters:
            id: An optional, user-provided ID for the code block.
            session: An optional session name.
            title: An optional title.

        Returns:
            A unique identifier, usable as a pseudo-filename in tracebacks.
        """
        with self._lock:
            self._counter[session] += 1
            count = self._counter[session]
        if id:
            code_block_id = f"id {id}"
        elif session:
            code_block_id = f"session {session}; n{count}"
            if title:
                code_block_id = f"{code_block_id}; title {title}"
        else:
            code_block_id = f"n{count}"
            if title:
                code_block_id = f"{code_block_id}; title {title}"
        return f"<code block: {code_block_id}>"

    def globals_for(self, session: str | None) -> dict:
        """Return the globals dictionary for the given session.

        Parameters:
            session: A session name, or `None` for a one-off execution.

        Returns:
            The persistent globals of the session, or a fresh dictionary.
        """
        if not session:
            return {}
        with self._lock:
            return self._globals[session]

    def record_block(self, block_id: str, code: str) -> None:
        """Record the source lines of an executed block, for source mapping.

        Parameters:
            block_id: The identifier of the executed code block.
            code: The source code, as written in the original fence.
        """
        with self._lock:
            self._code_blocks[block_id] = code.split("\n")

    def source_line(self, block_id: str, lineno: int) -> str:
        """Return the source line of a recorded block, pointing back to the original fence.

        Parameters:
            block_id: The identifier of the executed code block.
            lineno: The line number within the block (1-based).

        Returns:
            The source line as written in the original fence.
        """
        return self._code_blocks[block_id][lineno - 1]

    def close(self) -> None:
        """Drop all owned state: session globals, block counters and recorded sources."""
        with self._lock:
            self._globals = defaultdict(dict)
            self._counter = defaultdict(int)
            self._code_blocks = {}


session_manager = SessionManager()
"""The default session manager, shared by all runners unless overridden."""
