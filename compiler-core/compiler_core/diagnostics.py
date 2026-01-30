from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Span:
    line_start: int
    column_start: int
    line_end: int
    column_end: int


@dataclass
class Diagnostic:
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    span: Optional[Span] = None

    def __str__(self) -> str:
        if self.span is not None:
            return f"L{self.span.line_start}:{self.span.column_start} {self.message}"
        if self.line is None:
            return self.message
        return f"L{self.line}:{self.column or 0} {self.message}"


def format_diagnostic(diag: Diagnostic, source: str) -> str:
    if diag.span is None:
        return str(diag)
    lines = source.splitlines()
    line_index = diag.span.line_start - 1
    if line_index < 0 or line_index >= len(lines):
        return str(diag)
    line = lines[line_index]
    start = max(diag.span.column_start - 1, 0)
    end = max(diag.span.column_end - 1, start + 1)
    caret = " " * start + "^" * max(1, end - start)
    return "\n".join([str(diag), line, caret])


