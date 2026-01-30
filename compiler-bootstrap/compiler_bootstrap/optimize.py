from __future__ import annotations

from typing import Dict

from compiler_core import ir


class Optimizer:
    def run(self, module: ir.IRModule) -> ir.IRModule:
        self._inline(module)
        for func in module.functions:
            self._const_fold(func)
            self._simplify_arith(func)
            self._loop_opt(func)
            self._dce(func)
        return module

    def _inline(self, module: ir.IRModule) -> None:
        inlineable = self._collect_inlineable(module)
        if not inlineable:
            return
        for func in module.functions:
            for block in func.blocks:
                new_instrs: list[ir.Instr] = []
                for instr in block.instructions:
                    if instr.op == "call":
                        callee = instr.args[0]
                        args = instr.args[1:]
                        if callee in inlineable:
                            kind, payload = inlineable[callee]
                            if kind == "const":
                                new_instrs.append(ir.Instr(op="const", args=[payload], result=instr.result, type_name="int"))
                                continue
                            if kind == "arg":
                                idx = payload
                                if idx < len(args):
                                    new_instrs.append(ir.Instr(op="assign", args=[args[idx]], result=instr.result))
                                    continue
                    new_instrs.append(instr)
                block.instructions = new_instrs

    def _collect_inlineable(self, module: ir.IRModule) -> Dict[str, tuple[str, int | str]]:
        inlineable: Dict[str, tuple[str, int | str]] = {}
        for func in module.functions:
            if func.name == "main":
                continue
            if len(func.blocks) != 1:
                continue
            block = func.blocks[0]
            if not block.instructions:
                continue
            if block.instructions[-1].op != "ret":
                continue
            if any(i.op in ("print", "buf_create", "buf_borrow", "release", "loop_begin", "loop_end", "if_begin", "if_else", "if_end") for i in block.instructions):
                continue
            if any(i.op == "call" for i in block.instructions[:-1]):
                continue
            ret_arg = block.instructions[-1].args[0]
            params = [p.name for p in func.params]
            if ret_arg in params:
                inlineable[func.name] = ("arg", params.index(ret_arg))
                continue
            const_value = self._find_const_value(block.instructions, ret_arg)
            if const_value is not None:
                inlineable[func.name] = ("const", const_value)
        return inlineable

    def _find_const_value(self, instrs: list[ir.Instr], name: str) -> str | None:
        for instr in instrs:
            if instr.result == name and instr.op == "const":
                return instr.args[0]
        return None

    def _const_fold(self, func: ir.IRFunction) -> None:
        consts: Dict[str, str] = {}
        for block in func.blocks:
            for instr in block.instructions:
                if instr.op == "const":
                    consts[instr.result] = instr.args[0]
                elif instr.op == "assign":
                    if instr.args[0] in consts:
                        consts[instr.result] = consts[instr.args[0]]
                elif instr.op == "add":
                    left, right = instr.args
                    if left in consts and right in consts:
                        instr.op = "const"
                        instr.args = [str(int(consts[left]) + int(consts[right]))]
                        consts[instr.result] = instr.args[0]
                elif instr.op == "sub":
                    left, right = instr.args
                    if left in consts and right in consts:
                        instr.op = "const"
                        instr.args = [str(int(consts[left]) - int(consts[right]))]
                        consts[instr.result] = instr.args[0]
                elif instr.op == "mul":
                    left, right = instr.args
                    if left in consts and right in consts:
                        instr.op = "const"
                        instr.args = [str(int(consts[left]) * int(consts[right]))]
                        consts[instr.result] = instr.args[0]
                elif instr.op == "div":
                    left, right = instr.args
                    if left in consts and right in consts and int(consts[right]) != 0:
                        instr.op = "const"
                        instr.args = [str(int(consts[left]) // int(consts[right]))]
                        consts[instr.result] = instr.args[0]
                elif instr.op == "neg":
                    value = instr.args[0]
                    if value in consts:
                        instr.op = "const"
                        instr.args = [str(-int(consts[value]))]
                        consts[instr.result] = instr.args[0]
                elif instr.op == "call":
                    callee = instr.args[0]
                    args = instr.args[1:]
                    if callee in ("gt", "lt", "eq", "ge", "le", "ne") and len(args) == 2:
                        if args[0] in consts and args[1] in consts:
                            left = int(consts[args[0]])
                            right = int(consts[args[1]])
                            if callee == "gt":
                                value = 1 if left > right else 0
                            elif callee == "lt":
                                value = 1 if left < right else 0
                            elif callee == "eq":
                                value = 1 if left == right else 0
                            elif callee == "ge":
                                value = 1 if left >= right else 0
                            elif callee == "le":
                                value = 1 if left <= right else 0
                            else:
                                value = 1 if left != right else 0
                            instr.op = "const"
                            instr.args = [str(value)]
                            consts[instr.result] = instr.args[0]

    def _simplify_arith(self, func: ir.IRFunction) -> None:
        consts: Dict[str, int] = {}
        for block in func.blocks:
            new_instrs: list[ir.Instr] = []
            for instr in block.instructions:
                if instr.op == "const":
                    consts[instr.result] = int(instr.args[0])
                if instr.op == "assign" and instr.args[0] in consts:
                    consts[instr.result] = consts[instr.args[0]]
                if instr.op == "add":
                    left, right = instr.args
                    if left in consts and consts[left] == 0:
                        instr = ir.Instr(op="assign", args=[right], result=instr.result)
                    elif right in consts and consts[right] == 0:
                        instr = ir.Instr(op="assign", args=[left], result=instr.result)
                elif instr.op == "sub":
                    left, right = instr.args
                    if right in consts and consts[right] == 0:
                        instr = ir.Instr(op="assign", args=[left], result=instr.result)
                    elif left in consts and consts[left] == 0:
                        instr = ir.Instr(op="neg", args=[right], result=instr.result)
                elif instr.op == "mul":
                    left, right = instr.args
                    if left in consts and consts[left] == 0:
                        instr = ir.Instr(op="const", args=["0"], result=instr.result, type_name="int")
                        consts[instr.result] = 0
                    elif right in consts and consts[right] == 0:
                        instr = ir.Instr(op="const", args=["0"], result=instr.result, type_name="int")
                        consts[instr.result] = 0
                    elif left in consts and consts[left] == 1:
                        instr = ir.Instr(op="assign", args=[right], result=instr.result)
                    elif right in consts and consts[right] == 1:
                        instr = ir.Instr(op="assign", args=[left], result=instr.result)
                elif instr.op == "div":
                    left, right = instr.args
                    if right in consts and consts[right] == 1:
                        instr = ir.Instr(op="assign", args=[left], result=instr.result)
                elif instr.op == "neg":
                    value = instr.args[0]
                    if value in consts:
                        instr = ir.Instr(op="const", args=[str(-consts[value])], result=instr.result, type_name="int")
                        consts[instr.result] = -consts[value]
                new_instrs.append(instr)
            block.instructions = new_instrs

    def _loop_opt(self, func: ir.IRFunction) -> None:
        for block in func.blocks:
            i = 0
            consts: Dict[str, int] = {}
            new_instrs: list[ir.Instr] = []
            while i < len(block.instructions):
                instr = block.instructions[i]
                if instr.op == "const":
                    consts[instr.result] = int(instr.args[0])
                if instr.op == "assign" and instr.args[0] in consts:
                    consts[instr.result] = consts[instr.args[0]]
                if instr.op == "loop_begin":
                    loop_var, count_var = instr.args[0], instr.args[1]
                    count = consts.get(count_var)
                    if count is None:
                        new_instrs.append(instr)
                        i += 1
                        continue
                    # find matching loop_end
                    depth = 1
                    j = i + 1
                    while j < len(block.instructions):
                        if block.instructions[j].op == "loop_begin":
                            depth += 1
                        elif block.instructions[j].op == "loop_end":
                            depth -= 1
                            if depth == 0:
                                break
                        j += 1
                    if j >= len(block.instructions):
                        new_instrs.append(instr)
                        i += 1
                        continue
                    body = block.instructions[i + 1 : j]
                    if count == 0:
                        i = j + 1
                        continue
                    if count == 1:
                        for b in body:
                            if b.op == "inc":
                                continue
                            new_instrs.append(b)
                        i = j + 1
                        continue
                    if count <= 3 and not any(b.op == "loop_begin" for b in body):
                        for _ in range(count):
                            for b in body:
                                if b.op == "inc":
                                    continue
                                new_instrs.append(b)
                        i = j + 1
                        continue
                    if count > 3 and count % 2 == 0:
                        for _ in range(2):
                            for b in body:
                                if b.op == "inc":
                                    continue
                                new_instrs.append(b)
                        consts[count_var] = count // 2
                        i = j + 1
                        continue
                    new_instrs.append(instr)
                    i += 1
                    continue
                new_instrs.append(instr)
                i += 1
            block.instructions = new_instrs

    def _dce(self, func: ir.IRFunction) -> None:
        live: Dict[str, bool] = {}
        for block in func.blocks:
            new_instrs: list[ir.Instr] = []
            for instr in reversed(block.instructions):
                if self._is_side_effect(instr):
                    new_instrs.append(instr)
                    for arg in instr.args:
                        live[arg] = True
                    continue
                if instr.result and live.get(instr.result, False):
                    new_instrs.append(instr)
                    for arg in instr.args:
                        live[arg] = True
            block.instructions = list(reversed(new_instrs))

    def _is_side_effect(self, instr: ir.Instr) -> bool:
        if instr.op in ("print", "ret", "buf_create", "buf_borrow", "release"):
            return True
        if instr.op == "call":
            return True
        if instr.op in (
            "assign",
            "loop_begin",
            "loop_end",
            "if_begin",
            "if_else",
            "if_end",
            "inc",
            "while_begin",
            "while_end",
            "break",
            "continue",
        ):
            return True
        return False


