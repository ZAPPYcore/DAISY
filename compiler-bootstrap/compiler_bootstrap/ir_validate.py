from __future__ import annotations

from typing import Iterable, List

from compiler_core import ir


def validate_module(module: ir.IRModule) -> None:
    errors: List[str] = []
    for func in module.functions:
        errors.extend(_validate_function(func))
    if errors:
        joined = "\n".join(errors)
        raise RuntimeError(f"IR validation failed:\n{joined}")


def _validate_function(func: ir.IRFunction) -> List[str]:
    defined = {param.name for param in func.params}
    errors: List[str] = []
    for block in func.blocks:
        for instr in block.instructions:
            for arg in _uses(instr):
                if _is_literal(arg):
                    continue
                if arg not in defined:
                    errors.append(f"{func.name}: use before def `{arg}` in {instr.op}")
            if instr.result:
                defined.add(instr.result)
    return errors


def _uses(instr: ir.Instr) -> Iterable[str]:
    op = instr.op
    args = instr.args
    if op in ("const", "const_str", "if_else", "if_end", "while_end", "loop_end", "break", "continue"):
        return []
    if op == "assign":
        return args[:1]
    if op in ("add", "sub", "mul", "div"):
        return args[:2]
    if op == "neg":
        return args[:1]
    if op == "print":
        return args[:1]
    if op == "ret":
        return args[:1]
    if op == "call":
        return args[1:]
    if op == "struct_new":
        return args[1:]
    if op == "struct_get":
        return args[:1]
    if op == "struct_set":
        return [args[0], args[2]]
    if op == "enum_make":
        return args[2:]
    if op in ("enum_tag", "enum_payload"):
        return args[:1]
    if op == "buf_create":
        return args[:1]
    if op == "buf_borrow":
        return args[:3]
    if op == "borrow":
        return args[:2]
    if op in ("if_begin", "while_begin"):
        return args[:1]
    if op == "loop_begin":
        return args[:2]
    if op == "inc":
        return args[:1]
    return args


def _is_literal(value: str) -> bool:
    if value in ("0", "1"):
        return True
    try:
        int(value)
        return True
    except ValueError:
        return False

