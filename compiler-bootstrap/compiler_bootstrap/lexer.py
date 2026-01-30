from __future__ import annotations

from dataclasses import dataclass
from typing import List


KOREAN_PARTICLES = ("부터", "까지", "을", "를", "에", "의", "은", "는", "이", "가", "으로", "로")


@dataclass
class Line:
    indent: int
    text: str
    line: int


@dataclass
class Token:
    kind: str
    value: str
    line: int
    column: int


def tokenize_lines(source: str) -> List[Line]:
    lines: List[Line] = []
    for idx, raw in enumerate(source.splitlines(), start=1):
        if raw.strip() == "":
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        text = raw.rstrip("\n")
        content = text[indent:]
        if content.startswith("영어:") or content.startswith("한국어:"):
            cut = "영어:" if content.startswith("영어:") else "한국어:"
            content = content[len(cut) :].lstrip(" ")
            text = (" " * indent) + content
        lines.append(Line(indent=indent, text=text, line=idx))
    return lines


def tokenize(source: str) -> List[Token]:
    tokens: List[Token] = []
    indent_stack = [0]
    for line in tokenize_lines(source):
        indent = line.indent
        if indent % 2 != 0:
            raise ValueError(f"Indentation must be multiples of 2 spaces (line {line.line})")
        if indent > indent_stack[-1]:
            indent_stack.append(indent)
            tokens.append(Token(kind="INDENT", value="", line=line.line, column=1))
        while indent < indent_stack[-1]:
            indent_stack.pop()
            tokens.append(Token(kind="DEDENT", value="", line=line.line, column=1))
        tokens.extend(_tokenize_text(line.text, line.line))
        tokens.append(Token(kind="NEWLINE", value="", line=line.line, column=len(line.text) + 1))
    while len(indent_stack) > 1:
        indent_stack.pop()
        tokens.append(Token(kind="DEDENT", value="", line=len(tokens) + 1, column=1))
    tokens.append(Token(kind="EOF", value="", line=len(tokens) + 1, column=1))
    return tokens


def _tokenize_text(text: str, line: int) -> List[Token]:
    tokens: List[Token] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch == '"':
            start = i + 1
            i += 1
            while i < len(text) and text[i] != '"':
                if text[i] == "\\" and i + 1 < len(text):
                    i += 2
                    continue
                i += 1
            value = text[start:i]
            tokens.append(Token(kind="STRING", value=value, line=line, column=start))
            i += 1
            continue
        if ch.isdigit():
            start = i
            while i < len(text) and text[i].isdigit():
                i += 1
            tokens.append(Token(kind="NUMBER", value=text[start:i], line=line, column=start + 1))
            continue
        if _is_ident_start(ch):
            start = i
            while i < len(text) and _is_ident_part(text[i]):
                i += 1
            value = text[start:i]
            tokens.extend(_split_particles(value, line, start + 1))
            continue
        if ch == "-" and i + 1 < len(text) and text[i + 1] == ">":
            tokens.append(Token(kind="ARROW", value="->", line=line, column=i + 1))
            i += 2
            continue
        if i + 1 < len(text):
            two = text[i : i + 2]
            if two in ("==", "!=", ">=", "<=", "&&", "||"):
                tokens.append(Token(kind="OP", value=two, line=line, column=i + 1))
                i += 2
                continue
        if ch in ("(", ")", ":", ",", "."):
            tokens.append(Token(kind="PUNCT", value=ch, line=line, column=i + 1))
            i += 1
            continue
        if ch in ("=", "<", ">"):
            tokens.append(Token(kind="OP", value=ch, line=line, column=i + 1))
            i += 1
            continue
        if ch in ("+", "-", "*", "/"):
            tokens.append(Token(kind="OP", value=ch, line=line, column=i + 1))
            i += 1
            continue
        raise ValueError(f"Unexpected character '{ch}' at line {line}:{i + 1}")
    return tokens


def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_" or _is_korean(ch)


def _is_ident_part(ch: str) -> bool:
    return ch.isalnum() or ch == "_" or _is_korean(ch)


def _is_korean(ch: str) -> bool:
    return "가" <= ch <= "힣"


def _split_particles(value: str, line: int, column: int) -> List[Token]:
    for particle in KOREAN_PARTICLES:
        if value.endswith(particle) and len(value) > len(particle):
            stem = value[: -len(particle)]
            return [
                Token(kind="IDENT", value=stem, line=line, column=column),
                Token(kind="PART", value=particle, line=line, column=column + len(stem)),
            ]
    return [Token(kind="IDENT", value=value, line=line, column=column)]


