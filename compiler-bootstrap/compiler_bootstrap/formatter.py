from __future__ import annotations

from typing import List

from compiler_bootstrap.lexer import tokenize_lines


def format_source(source: str) -> str:
    lines = tokenize_lines(source)
    formatted: List[str] = []
    for line in lines:
        text = _normalize_spacing(line.text)
        formatted.append(" " * line.indent + text)
    return "\n".join(formatted) + "\n"


def _normalize_spacing(text: str) -> str:
    text = " ".join(text.strip().split())
    text = text.replace(" : ", ":")
    return text


