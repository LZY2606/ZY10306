from __future__ import annotations

from collections import defaultdict


class SessionManager:
    """Explicit owner of Python session state and code block source mapping.

    The session manager is the single place where execution state lives:
    session globals, code block counters and the mapping of code block
    identifiers back to their original source lines. State is dropped
    through the explicit [`close`][markdown_exec.SessionManager.close] and
    [`close_all`][markdown_exec.SessionManager.close_all] methods, so that
    consecutive builds never silently reuse stale sessions.
    """

    def __init__(self) -> None:
        self._globals: dict[str, dict] = defaultdict(dict)
        self._counter: dict[str | None, int] = defaultdict(int)
        self._code_blocks: dict[str, list[str]] = {}

    def block_id(self, identifier: str = "", session: str | None = None, title: str | None = None) -> str:
        """Compute a unique identifier for a code block.

        Parameters:
            identifier: An optional user-provided identifier.
            session: An optional session name.
            title: An optional code block title.

        Returns:
            A unique code block identifier.
        """
        self._counter[session] += 1
        if identifier:
            code_block_id = f"id {identifier}"
        elif session:
            code_block_id = f"session {session}; n{self._counter[session]}"
            if title:
                code_block_id = f"{code_block_id}; title {title}"
        else:
            code_block_id = f"n{self._counter[session]}"
            if title:
                code_block_id = f"{code_block_id}; title {title}"
        return f"<code block: {code_block_id}>"

    def globals_for(self, session: str | None) -> dict:
        """Return the globals dictionary for the given session.

        Parameters:
            session: A session name, or `None` for a throwaway dictionary.

        Returns:
            The session globals.
        """
        return self._globals[session] if session else {}

    def register_block(self, block_id: str, code: str) -> None:
        """Map a code block identifier to its original source lines.

        Parameters:
            block_id: The code block identifier.
            code: The source code of the block.
        """
        self._code_blocks[block_id] = code.split("\n")

    def source_line(self, filename: str, lineno: int) -> str:
        """Return the original source line for a code block frame.

        Parameters:
            filename: The code block identifier used as filename.
            lineno: The 1-based line number in the original fence.

        Returns:
            The original source line.
        """
        return self._code_blocks[filename][lineno - 1]

    def close(self, session: str) -> None:
        """Drop the state of a single session.

        Parameters:
            session: The session name to close.
        """
        self._globals.pop(session, None)

    def close_all(self) -> None:
        """Drop all session state, counters and source mappings."""
        self._globals.clear()
        self._counter.clear()
        self._code_blocks.clear()


session_manager = SessionManager()
"""The default session manager, shared by Python runners."""
