from __future__ import annotations

from typing import Dict, List

from compiler_core import ast, ir


class IRGen:
    def __init__(
        self,
        struct_defs: Dict[str, List[tuple[str, object]]] | None = None,
        enum_defs: Dict[str, List[tuple[str, object]]] | None = None,
        expr_types: Dict[int, object] | None = None,
    ) -> None:
        self.temp_index = 0
        self.struct_defs: Dict[str, List[ir.IRStructField]] = {}
        self.enum_defs: Dict[str, List[ir.IREnumCase]] = {}
        self.struct_names: set[str] = set()
        self._struct_defs_extra = struct_defs or {}
        self._enum_defs_extra = enum_defs or {}
        self.expr_types = expr_types or {}

    def lower_module(self, module: ast.Module) -> ir.IRModule:
        functions: List[ir.IRFunction] = []
        externs: List[ir.IRExtern] = []
        structs: List[ir.IRStruct] = []
        enums: List[ir.IREnum] = []
        self.struct_defs = {}
        self.enum_defs = {}
        self.struct_names = set()
        for name, fields in self._struct_defs_extra.items():
            ir_fields = [ir.IRStructField(name=f_name, type_name=f_type.name) for f_name, f_type in fields]
            structs.append(ir.IRStruct(name=name, fields=ir_fields))
            self.struct_defs[name] = ir_fields
            self.struct_names.add(name)
        for name, cases in self._enum_defs_extra.items():
            ir_cases = [ir.IREnumCase(name=c_name, payload=c_payload.name if c_payload else None) for c_name, c_payload in cases]
            enums.append(ir.IREnum(name=name, cases=ir_cases))
            self.enum_defs[name] = ir_cases
        for stmt in module.body:
            if isinstance(stmt, ast.FunctionDef):
                if stmt.type_params:
                    continue
                functions.append(self._lower_function(stmt))
            elif isinstance(stmt, ast.ExternFunctionDef):
                externs.append(
                    ir.IRExtern(
                        name=stmt.name,
                        params=[ir.IRParam(name=p.name, type_name=p.type_ref.name) for p in stmt.params],
                        return_type=stmt.return_type.name,
                    )
                )
            elif isinstance(stmt, ast.StructDef):
                if stmt.type_params:
                    continue
                fields = [ir.IRStructField(name=f.name, type_name=f.type_ref.name) for f in stmt.fields]
                if stmt.name not in self.struct_defs:
                    structs.append(ir.IRStruct(name=stmt.name, fields=fields))
                    self.struct_defs[stmt.name] = fields
                self.struct_names.add(stmt.name)
            elif isinstance(stmt, ast.EnumDef):
                if stmt.type_params:
                    continue
                cases = [ir.IREnumCase(name=c.name, payload=c.payload.name if c.payload else None) for c in stmt.cases]
                if stmt.name not in self.enum_defs:
                    enums.append(ir.IREnum(name=stmt.name, cases=cases))
                    self.enum_defs[stmt.name] = cases
            elif isinstance(stmt, ast.TraitDef):
                continue
            elif isinstance(stmt, ast.ImplDef):
                continue
        return ir.IRModule(name=module.name, functions=functions, externs=externs, structs=structs, enums=enums)

    def _lower_function(self, func: ast.FunctionDef) -> ir.IRFunction:
        params = [ir.IRParam(name=p.name, type_name=p.type_ref.name) for p in func.params]
        blocks = [ir.BasicBlock(label="entry", instructions=[])]
        for stmt in func.body:
            self._lower_stmt(stmt, blocks[0])
        has_ret = any(instr.op == "ret" for instr in blocks[0].instructions)
        if not has_ret:
            blocks[0].instructions.append(ir.Instr(op="ret", args=["0"]))
        return ir.IRFunction(name=func.name, params=params, return_type=func.return_type.name, blocks=blocks)

    def _lower_stmt(self, stmt: ast.Stmt, block: ir.BasicBlock) -> None:
        if isinstance(stmt, ast.Assign):
            value = self._lower_expr(stmt.value, block)
            if isinstance(stmt.target, ast.Name):
                if stmt.target.value != "_":
                    block.instructions.append(ir.Instr(op="assign", args=[value], result=stmt.target.value))
            elif isinstance(stmt.target, ast.MemberAccess):
                base = self._lower_expr(stmt.target.value, block)
                block.instructions.append(ir.Instr(op="struct_set", args=[base, stmt.target.name, value]))
        elif isinstance(stmt, ast.AddAssign):
            target = self._lower_expr(stmt.target, block)
            value = self._lower_expr(stmt.value, block)
            temp = self._temp()
            block.instructions.append(ir.Instr(op="add", args=[target, value], result=temp, type_name="int"))
            if isinstance(stmt.target, ast.Name):
                block.instructions.append(ir.Instr(op="assign", args=[temp], result=stmt.target.value))
        elif isinstance(stmt, ast.Print):
            value = self._lower_expr(stmt.value, block)
            block.instructions.append(ir.Instr(op="print", args=[value]))
        elif isinstance(stmt, ast.Return):
            if stmt.value:
                value = self._lower_expr(stmt.value, block)
                block.instructions.append(ir.Instr(op="ret", args=[value]))
            else:
                block.instructions.append(ir.Instr(op="ret", args=["0"]))
        elif isinstance(stmt, ast.BufferCreate):
            size = self._lower_expr(stmt.size, block)
            block.instructions.append(ir.Instr(op="buf_create", args=[size], result=stmt.name, type_name="buffer"))
        elif isinstance(stmt, ast.BorrowSlice):
            buffer_name = self._lower_expr(stmt.buffer, block)
            start = self._lower_expr(stmt.start, block)
            end = self._lower_expr(stmt.end, block)
            block.instructions.append(
                ir.Instr(op="buf_borrow", args=[buffer_name, start, end, "1" if stmt.mutable else "0"], result=stmt.name, type_name="view")
            )
        elif isinstance(stmt, ast.If):
            cond = self._lower_expr(stmt.condition, block)
            block.instructions.append(ir.Instr(op="if_begin", args=[cond]))
            then_block = ir.BasicBlock(label=f"if_{self._temp()}", instructions=[])
            for inner in stmt.body:
                self._lower_stmt(inner, then_block)
            block.instructions.extend(then_block.instructions)
            if stmt.else_body:
                block.instructions.append(ir.Instr(op="if_else"))
                else_block = ir.BasicBlock(label=f"else_{self._temp()}", instructions=[])
                for inner in stmt.else_body:
                    self._lower_stmt(inner, else_block)
                block.instructions.extend(else_block.instructions)
            block.instructions.append(ir.Instr(op="if_end"))
        elif isinstance(stmt, ast.Repeat):
            count = self._lower_expr(stmt.count, block)
            loop_var = self._temp()
            block.instructions.append(ir.Instr(op="const", args=["0"], result=loop_var, type_name="int"))
            block.instructions.append(ir.Instr(op="loop_begin", args=[loop_var, count]))
            loop_block = ir.BasicBlock(label=f"loop_{self._temp()}", instructions=[])
            for inner in stmt.body:
                self._lower_stmt(inner, loop_block)
            loop_block.instructions.append(ir.Instr(op="inc", args=[loop_var]))
            block.instructions.extend(loop_block.instructions)
            block.instructions.append(ir.Instr(op="loop_end"))
        elif isinstance(stmt, ast.While):
            cond_var = self._lower_expr(stmt.condition, block)
            block.instructions.append(ir.Instr(op="while_begin", args=[cond_var]))
            loop_block = ir.BasicBlock(label=f"while_{self._temp()}", instructions=[])
            for inner in stmt.body:
                self._lower_stmt(inner, loop_block)
            next_cond = self._lower_expr(stmt.condition, loop_block)
            loop_block.instructions.append(ir.Instr(op="assign", args=[next_cond], result=cond_var))
            block.instructions.extend(loop_block.instructions)
            block.instructions.append(ir.Instr(op="while_end"))
        elif isinstance(stmt, ast.Match):
            match_val = self._lower_expr(stmt.value, block)
            enum_name = self._match_enum_name(stmt)
            match_tag = None
            if enum_name:
                match_tag = self._temp()
                block.instructions.append(ir.Instr(op="enum_tag", args=[match_val], result=match_tag))
            matched = self._temp()
            block.instructions.append(ir.Instr(op="const", args=["0"], result=matched, type_name="int"))
            for case in stmt.cases:
                matched_cond = self._temp()
                block.instructions.append(ir.Instr(op="call", args=["eq", matched, "0"], result=matched_cond))
                block.instructions.append(ir.Instr(op="if_begin", args=[matched_cond]))
                case_block = ir.BasicBlock(label=f"match_{self._temp()}", instructions=[])
                self._lower_match_case(case, match_val, enum_name, match_tag, matched, case_block)
                block.instructions.extend(case_block.instructions)
                block.instructions.append(ir.Instr(op="if_end"))
            if stmt.else_body:
                cond = self._temp()
                block.instructions.append(ir.Instr(op="call", args=["eq", matched, "0"], result=cond))
                block.instructions.append(ir.Instr(op="if_begin", args=[cond]))
                else_block = ir.BasicBlock(label=f"match_{self._temp()}", instructions=[])
                for inner in stmt.else_body:
                    self._lower_stmt(inner, else_block)
                block.instructions.extend(else_block.instructions)
                block.instructions.append(ir.Instr(op="if_end"))
        elif isinstance(stmt, ast.UnsafeBlock):
            for inner in stmt.body:
                self._lower_stmt(inner, block)
        elif isinstance(stmt, ast.Move):
            src = self._lower_expr(stmt.src, block)
            block.instructions.append(ir.Instr(op="assign", args=[src], result=stmt.dst))
        elif isinstance(stmt, ast.Release):
            target = self._lower_expr(stmt.target, block)
            block.instructions.append(ir.Instr(op="release", args=[target]))
        elif isinstance(stmt, ast.Break):
            block.instructions.append(ir.Instr(op="break"))
        elif isinstance(stmt, ast.Continue):
            block.instructions.append(ir.Instr(op="continue"))
        elif isinstance(stmt, ast.Import):
            return
        elif isinstance(stmt, ast.StructDef):
            return
        elif isinstance(stmt, ast.EnumDef):
            return

    def _match_enum_name(self, stmt: ast.Match) -> str | None:
        enum_name = None
        for case in stmt.cases:
            if isinstance(case.pattern, ast.WildcardPattern):
                continue
            if not isinstance(case.pattern, ast.EnumPattern):
                return None
            case_enum = case.pattern.enum_name
            if case_enum not in self.enum_defs:
                return None
            if enum_name is None:
                enum_name = case_enum
            elif enum_name != case_enum:
                return None
        return enum_name

    def _enum_case_index(self, enum_name: str, case_name: str) -> int:
        enum_cases = self.enum_defs.get(enum_name, [])
        for idx, case in enumerate(enum_cases):
            if case.name == case_name:
                return idx
        return -1

    def _emit_if(self, block: ir.BasicBlock, cond: str, emit_body) -> None:
        block.instructions.append(ir.Instr(op="if_begin", args=[cond]))
        emit_body()
        block.instructions.append(ir.Instr(op="if_end"))

    def _emit_enum_payload(self, block: ir.BasicBlock, value_var: str, case_name: str, target: str) -> None:
        block.instructions.append(ir.Instr(op="enum_payload", args=[value_var, case_name], result=target))

    def _emit_guarded_body(self, case: ast.MatchCase, matched: str, block: ir.BasicBlock) -> None:
        def emit_body() -> None:
            for inner in case.body:
                self._lower_stmt(inner, block)
            block.instructions.append(ir.Instr(op="assign", args=["1"], result=matched))

        if case.guard:
            guard_val = self._lower_expr(case.guard, block)
            self._emit_if(block, guard_val, emit_body)
        else:
            emit_body()

    def _emit_pattern_match(self, pattern: ast.Pattern, value_var: str, emit_body, block: ir.BasicBlock) -> None:
        if isinstance(pattern, ast.WildcardPattern):
            emit_body()
            return
        if isinstance(pattern, ast.BindPattern):
            block.instructions.append(ir.Instr(op="assign", args=[value_var], result=pattern.name))
            emit_body()
            return
        if isinstance(pattern, ast.LiteralPattern):
            lit_val = self._lower_expr(pattern.value, block)
            cond = self._temp()
            block.instructions.append(ir.Instr(op="call", args=["eq", value_var, lit_val], result=cond))
            self._emit_if(block, cond, emit_body)
            return
        if isinstance(pattern, ast.StructPattern):
            fields = self.struct_defs.get(pattern.struct_name, [])
            field_patterns = pattern.fields
            if not fields or len(fields) != len(field_patterns):
                return

            def emit_field(idx: int) -> None:
                if idx >= len(field_patterns):
                    emit_body()
                    return
                field = fields[idx]
                field_val = self._temp()
                block.instructions.append(ir.Instr(op="struct_get", args=[value_var, field.name], result=field_val))
                self._emit_pattern_match(field_patterns[idx], field_val, lambda: emit_field(idx + 1), block)

            emit_field(0)
            return
        if isinstance(pattern, ast.EnumPattern):
            tag = self._temp()
            block.instructions.append(ir.Instr(op="enum_tag", args=[value_var], result=tag))
            case_index = self._enum_case_index(pattern.enum_name, pattern.case_name)
            cond = self._temp()
            block.instructions.append(ir.Instr(op="call", args=["eq", tag, str(case_index)], result=cond))

            def emit_case() -> None:
                if pattern.binding:
                    self._emit_enum_payload(block, value_var, pattern.case_name, pattern.binding)
                    emit_body()
                    return
                if pattern.payload:
                    payload_tmp = self._temp()
                    self._emit_enum_payload(block, value_var, pattern.case_name, payload_tmp)
                    self._emit_pattern_match(pattern.payload, payload_tmp, emit_body, block)
                    return
                emit_body()

            self._emit_if(block, cond, emit_case)

    def _lower_match_case(
        self,
        case: ast.MatchCase,
        match_val: str,
        enum_name: str | None,
        match_tag: str | None,
        matched: str,
        block: ir.BasicBlock,
    ) -> None:
        if enum_name:
            if isinstance(case.pattern, ast.WildcardPattern):
                self._emit_guarded_body(case, matched, block)
                return
            if isinstance(case.pattern, ast.EnumPattern) and match_tag is not None:
                case_index = self._enum_case_index(enum_name, case.pattern.case_name)
                cond = self._temp()
                block.instructions.append(ir.Instr(op="call", args=["eq", match_tag, str(case_index)], result=cond))

                def emit_case() -> None:
                    if case.pattern.binding:
                        self._emit_enum_payload(block, match_val, case.pattern.case_name, case.pattern.binding)
                        self._emit_guarded_body(case, matched, block)
                        return
                    if case.pattern.payload:
                        payload_tmp = self._temp()
                        self._emit_enum_payload(block, match_val, case.pattern.case_name, payload_tmp)
                        self._emit_pattern_match(case.pattern.payload, payload_tmp, lambda: self._emit_guarded_body(case, matched, block), block)
                        return
                    self._emit_guarded_body(case, matched, block)

                self._emit_if(block, cond, emit_case)
                return
        else:
            if isinstance(case.pattern, ast.WildcardPattern):
                self._emit_guarded_body(case, matched, block)
                return
            if isinstance(case.pattern, ast.LiteralPattern):
                case_val = self._lower_expr(case.pattern.value, block)
                cond = self._temp()
                block.instructions.append(ir.Instr(op="call", args=["eq", match_val, case_val], result=cond))
                self._emit_if(block, cond, lambda: self._emit_guarded_body(case, matched, block))
                return
            if isinstance(case.pattern, (ast.StructPattern, ast.BindPattern)):
                self._emit_pattern_match(case.pattern, match_val, lambda: self._emit_guarded_body(case, matched, block), block)
                return

    def _lower_expr(self, expr: ast.Expr, block: ir.BasicBlock) -> str:
        if isinstance(expr, ast.IntLit):
            temp = self._temp()
            block.instructions.append(ir.Instr(op="const", args=[str(expr.value)], result=temp, type_name="int"))
            return temp
        if isinstance(expr, ast.StringLit):
            temp = self._temp()
            block.instructions.append(ir.Instr(op="const_str", args=[expr.value], result=temp, type_name="string"))
            return temp
        if isinstance(expr, ast.BoolLit):
            temp = self._temp()
            block.instructions.append(ir.Instr(op="const", args=["1" if expr.value else "0"], result=temp, type_name="bool"))
            return temp
        if isinstance(expr, ast.Name):
            return expr.value
        if isinstance(expr, ast.Call):
            args = [self._lower_expr(arg, block) for arg in expr.args]
            temp = self._temp()
            if expr.callee in self.struct_defs or expr.callee in self.struct_names:
                block.instructions.append(ir.Instr(op="struct_new", args=[expr.callee] + args, result=temp, type_name=expr.callee))
                return temp
            if "." in expr.callee:
                enum_name, case_name = expr.callee.split(".", 1)
                if enum_name in self.enum_defs:
                    block.instructions.append(ir.Instr(op="enum_make", args=[enum_name, case_name] + args, result=temp, type_name=enum_name))
                    return temp
            block.instructions.append(ir.Instr(op="call", args=[expr.callee] + args, result=temp))
            return temp
        if isinstance(expr, ast.MemberAccess):
            base = self._lower_expr(expr.value, block)
            temp = self._temp()
            block.instructions.append(ir.Instr(op="struct_get", args=[base, expr.name], result=temp))
            return temp
        if isinstance(expr, ast.BinOp):
            left = self._lower_expr(expr.left, block)
            right = self._lower_expr(expr.right, block)
            temp = self._temp()
            op_map = {"+": "add", "-": "sub", "*": "mul", "/": "div"}
            op = op_map.get(expr.op)
            if op is None:
                block.instructions.append(ir.Instr(op="const", args=["0"], result=temp, type_name="int"))
                return temp
            block.instructions.append(ir.Instr(op=op, args=[left, right], result=temp, type_name="int"))
            return temp
        if isinstance(expr, ast.UnaryOp):
            value = self._lower_expr(expr.value, block)
            if expr.op == "+":
                return value
            temp = self._temp()
            block.instructions.append(ir.Instr(op="neg", args=[value], result=temp, type_name="int"))
            return temp
        if isinstance(expr, ast.LogicalOp):
            left = self._lower_expr(expr.left, block)
            result = self._temp()
            if expr.op == "and":
                block.instructions.append(ir.Instr(op="const", args=["0"], result=result, type_name="bool"))
                block.instructions.append(ir.Instr(op="if_begin", args=[left]))
                right = self._lower_expr(expr.right, block)
                block.instructions.append(ir.Instr(op="assign", args=[right], result=result))
                block.instructions.append(ir.Instr(op="if_end"))
                return result
            block.instructions.append(ir.Instr(op="assign", args=[left], result=result))
            cond = self._temp()
            block.instructions.append(ir.Instr(op="call", args=["eq", left, "0"], result=cond))
            block.instructions.append(ir.Instr(op="if_begin", args=[cond]))
            right = self._lower_expr(expr.right, block)
            block.instructions.append(ir.Instr(op="assign", args=[right], result=result))
            block.instructions.append(ir.Instr(op="if_end"))
            return result
        if isinstance(expr, ast.TryExpr):
            value = self._lower_expr(expr.value, block)
            type_info = self.expr_types.get(id(expr.value))
            type_name = type_info.name if type_info else ""
            base = type_name.split("__", 1)[0] if type_name else ""
            if base in ("Result", "Option") and type_name in self.enum_defs:
                err_case = "Err" if base == "Result" else "None"
                ok_case = "Ok" if base == "Result" else "Some"
                tag = self._temp()
                block.instructions.append(ir.Instr(op="enum_tag", args=[value], result=tag))
                err_index = self._enum_case_index(type_name, err_case)
                cond = self._temp()
                block.instructions.append(ir.Instr(op="call", args=["eq", tag, str(err_index)], result=cond))
                block.instructions.append(ir.Instr(op="if_begin", args=[cond]))
                block.instructions.append(ir.Instr(op="ret", args=[value]))
                block.instructions.append(ir.Instr(op="if_end"))
                ok_val = self._temp()
                block.instructions.append(ir.Instr(op="enum_payload", args=[value, ok_case], result=ok_val))
                return ok_val
            return value
        if isinstance(expr, ast.BorrowExpr):
            value = self._lower_expr(expr.value, block)
            temp = self._temp()
            block.instructions.append(ir.Instr(op="borrow", args=[value, "1" if expr.mutable else "0"], result=temp, type_name="view"))
            return temp
        if isinstance(expr, ast.CopyExpr):
            value = self._lower_expr(expr.value, block)
            temp = self._temp()
            block.instructions.append(ir.Instr(op="assign", args=[value], result=temp))
            return temp
        temp = self._temp()
        block.instructions.append(ir.Instr(op="const", args=["0"], result=temp, type_name="int"))
        return temp

    def _temp(self) -> str:
        self.temp_index += 1
        return f"t_{self.temp_index}"


