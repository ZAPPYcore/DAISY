from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "compiler-bootstrap"))
sys.path.insert(0, str(ROOT / "compiler-core"))

from compiler_bootstrap import borrowcheck, parser, typecheck  # noqa: E402
from compiler_core import ast, diagnostics  # noqa: E402


def read_message() -> dict:
    header = ""
    while True:
        line = sys.stdin.readline()
        if line == "\r\n" or line == "\n":
            break
        header += line
    length = 0
    for h in header.splitlines():
        if h.lower().startswith("content-length:"):
            length = int(h.split(":")[1].strip())
    body = sys.stdin.read(length)
    return json.loads(body)


def send_message(payload: dict) -> None:
    data = json.dumps(payload)
    sys.stdout.write(f"Content-Length: {len(data)}\r\n\r\n{data}")
    sys.stdout.flush()


def main() -> int:
    documents: Dict[str, str] = {}
    while True:
        msg = read_message()
        method = msg.get("method")
        if method == "initialize":
            send_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "result": {
                        "capabilities": {
                            "textDocumentSync": 1,
                            "hoverProvider": True,
                            "definitionProvider": True,
                        }
                    },
                }
            )
        elif method == "shutdown":
            send_message({"jsonrpc": "2.0", "id": msg.get("id"), "result": None})
        elif method == "exit":
            return 0
        elif method == "textDocument/didOpen":
            params = msg.get("params", {})
            doc = params.get("textDocument", {})
            uri = doc.get("uri")
            text = doc.get("text", "")
            if isinstance(uri, str):
                documents[uri] = text
                _publish_diagnostics(uri, _analyze(text))
        elif method == "textDocument/didChange":
            params = msg.get("params", {})
            doc = params.get("textDocument", {})
            uri = doc.get("uri")
            changes = params.get("contentChanges", [])
            if isinstance(uri, str) and changes:
                text = changes[0].get("text", "")
                documents[uri] = text
                _publish_diagnostics(uri, _analyze(text))
        elif method == "textDocument/hover":
            params = msg.get("params", {})
            doc = params.get("textDocument", {})
            uri = doc.get("uri")
            pos = params.get("position", {})
            if isinstance(uri, str):
                text = documents.get(uri, "")
                contents = _hover(text, pos.get("line"), pos.get("character"))
                send_message({"jsonrpc": "2.0", "id": msg.get("id"), "result": contents})
            else:
                send_message({"jsonrpc": "2.0", "id": msg.get("id"), "result": None})
        elif method == "textDocument/definition":
            params = msg.get("params", {})
            doc = params.get("textDocument", {})
            uri = doc.get("uri")
            pos = params.get("position", {})
            if isinstance(uri, str):
                text = documents.get(uri, "")
                location = _definition(uri, text, pos.get("line"), pos.get("character"))
                send_message({"jsonrpc": "2.0", "id": msg.get("id"), "result": location})
            else:
                send_message({"jsonrpc": "2.0", "id": msg.get("id"), "result": None})
        else:
            if "id" in msg:
                send_message({"jsonrpc": "2.0", "id": msg.get("id"), "result": None})


if __name__ == "__main__":
    raise SystemExit(main())


def _analyze(source: str) -> List[dict]:
    try:
        module = parser.parse(source)
    except Exception as exc:  # ParseError or ValueError
        return [_diag_from_parse_error(str(exc))]
    checker = typecheck.TypeChecker()
    type_info = checker.check_module(module)
    diagnostics_list: List[diagnostics.Diagnostic] = []
    diagnostics_list.extend(checker.errors)
    borrow = borrowcheck.BorrowChecker(type_info)
    borrow.check_module(module)
    diagnostics_list.extend(borrow.errors)
    return [_to_lsp_diag(d) for d in diagnostics_list]


def _diag_from_parse_error(message: str) -> dict:
    span = _parse_span_from_message(message)
    return _to_lsp_diag(diagnostics.Diagnostic(message=message, span=span))


def _parse_span_from_message(message: str) -> Optional[diagnostics.Span]:
    if not message.startswith("L"):
        return None
    try:
        head = message.split(" ", 1)[0]
        line_col = head[1:].split(":")
        line = int(line_col[0])
        col = int(line_col[1]) if len(line_col) > 1 else 1
        return diagnostics.Span(line, col, line, col + 1)
    except (ValueError, IndexError):
        return None


def _to_lsp_diag(diag: diagnostics.Diagnostic) -> dict:
    span = diag.span or diagnostics.Span(1, 1, 1, 2)
    return {
        "range": {
            "start": {"line": max(span.line_start - 1, 0), "character": max(span.column_start - 1, 0)},
            "end": {"line": max(span.line_end - 1, 0), "character": max(span.column_end - 1, 0)},
        },
        "severity": 1,
        "message": diag.message,
    }


def _publish_diagnostics(uri: str, diagnostics_list: List[dict]) -> None:
    send_message(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {"uri": uri, "diagnostics": diagnostics_list},
        }
    )


def _hover(source: str, line: Optional[int], character: Optional[int]) -> Optional[dict]:
    if line is None or character is None:
        return None
    word = _word_at(source, line, character)
    if not word:
        return None
    info = _symbol_info(source, word)
    if not info:
        return None
    return {"contents": {"kind": "markdown", "value": info}}


def _definition(uri: str, source: str, line: Optional[int], character: Optional[int]) -> Optional[dict]:
    if line is None or character is None:
        return None
    word = _word_at(source, line, character)
    if not word:
        return None
    span = _symbol_span(source, word)
    if span is None:
        return None
    return {
        "uri": uri,
        "range": {
            "start": {"line": max(span.line_start - 1, 0), "character": max(span.column_start - 1, 0)},
            "end": {"line": max(span.line_end - 1, 0), "character": max(span.column_end - 1, 0)},
        },
    }


def _symbol_info(source: str, word: str) -> Optional[str]:
    try:
        module = parser.parse(source)
    except Exception:
        return None
    name = word.split(".", 1)[-1]
    for stmt in module.body:
        if isinstance(stmt, (ast.FunctionDef, ast.ExternFunctionDef)) and stmt.name == name:
            params = ", ".join([f"{p.name}: {p.type_ref.name}" for p in stmt.params])
            return f"**fn {stmt.name}**({params}) -> {stmt.return_type.name}"
    return None


def _symbol_span(source: str, word: str) -> Optional[diagnostics.Span]:
    try:
        module = parser.parse(source)
    except Exception:
        return None
    name = word.split(".", 1)[-1]
    for stmt in module.body:
        if isinstance(stmt, (ast.FunctionDef, ast.ExternFunctionDef)) and stmt.name == name:
            return stmt.span
    return None


def _word_at(source: str, line: int, character: int) -> Optional[str]:
    lines = source.splitlines()
    if line < 0 or line >= len(lines):
        return None
    text = lines[line]
    if character < 0 or character > len(text):
        return None
    start = character
    while start > 0 and _is_word_char(text[start - 1]):
        start -= 1
    end = character
    while end < len(text) and _is_word_char(text[end]):
        end += 1
    word = text[start:end].strip()
    return word or None


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_" or _is_korean(ch) or ch == "."


def _is_korean(ch: str) -> bool:
    return "가" <= ch <= "힣"


