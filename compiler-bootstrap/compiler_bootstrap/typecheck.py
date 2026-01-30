from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from compiler_core import ast, diagnostics, types


@dataclass
class TypeInfo:
    expr_types: Dict[int, types.Type]
    var_types: Dict[str, types.Type]


@dataclass
class FuncSig:
    params: List[types.Type]
    returns: types.Type


class TypeChecker:
    def __init__(
        self,
        external_sigs: Optional[Dict[str, FuncSig]] = None,
        external_types: Optional[Dict[str, types.Type]] = None,
        external_structs: Optional[Dict[str, List[tuple[str, types.Type]]]] = None,
        external_enums: Optional[Dict[str, List[tuple[str, Optional[types.Type]]]]] = None,
        external_generic_funcs: Optional[Dict[str, ast.FunctionDef]] = None,
    ) -> None:
        self.errors: List[diagnostics.Diagnostic] = []
        self.expr_types: Dict[int, types.Type] = {}
        self.var_types: Dict[str, types.Type] = {}
        self.loop_depth = 0
        self.func_sigs: Dict[str, FuncSig] = {}
        self.external_sigs: Dict[str, FuncSig] = external_sigs or {}
        self.module_name = ""
        self.import_aliases: Dict[str, str] = {}
        self.use_modules: List[str] = []
        self.struct_defs: Dict[str, List[tuple[str, types.Type]]] = {}
        self.enum_defs: Dict[str, List[tuple[str, Optional[types.Type]]]] = {}
        self.custom_types: Dict[str, types.Type] = {}
        self.external_types: Dict[str, types.Type] = external_types or {}
        self.external_structs: Dict[str, List[tuple[str, types.Type]]] = external_structs or {}
        self.external_enums: Dict[str, List[tuple[str, Optional[types.Type]]]] = external_enums or {}
        self.external_generic_funcs: Dict[str, ast.FunctionDef] = external_generic_funcs or {}
        self.generic_structs: Dict[str, tuple[List[ast.TypeParam], List[tuple[str, ast.TypeRef]]]] = {}
        self.generic_enums: Dict[str, tuple[List[ast.TypeParam], List[tuple[str, Optional[ast.TypeRef]]]]] = {}
        self.generic_funcs: Dict[str, ast.FunctionDef] = {}
        self.specialized_functions: List[ast.FunctionDef] = []
        self.impl_functions: List[ast.FunctionDef] = []
        self.trait_defs: Dict[str, tuple[List[ast.TypeParam], Dict[str, FuncSig]]] = {}
        self.impl_methods: Dict[str, Dict[str, tuple[str, FuncSig]]] = {}
        self.impl_traits: Dict[str, set[str]] = {}
        self.current_return_type: Optional[types.Type] = None
        self.builtin_sigs: Dict[str, FuncSig] = {
            "str_len": FuncSig([types.STRING], types.INT),
            "str_char_at": FuncSig([types.STRING, types.INT], types.INT),
            "str_find_char": FuncSig([types.STRING, types.INT, types.INT], types.INT),
            "str_starts_with": FuncSig([types.STRING, types.STRING], types.BOOL),
            "str_to_int": FuncSig([types.STRING], types.INT),
            "str_substr": FuncSig([types.STRING, types.INT, types.INT], types.STRING),
            "str_trim": FuncSig([types.STRING], types.STRING),
            "str_concat": FuncSig([types.STRING, types.STRING], types.STRING),
            "str_release": FuncSig([types.STRING], types.UNIT),
            "file_read": FuncSig([types.STRING], types.STRING),
            "file_write": FuncSig([types.STRING, types.STRING], types.INT),
            "module_load": FuncSig([types.STRING], types.STRING),
            "error_last": FuncSig([], types.STRING),
            "error_clear": FuncSig([], types.UNIT),
            "panic": FuncSig([types.STRING], types.UNIT),
            "vec_new": FuncSig([], types.VEC),
            "vec_push": FuncSig([types.VEC, types.INT], types.UNIT),
            "vec_get": FuncSig([types.VEC, types.INT], types.INT),
            "vec_len": FuncSig([types.VEC], types.INT),
            "vec_release": FuncSig([types.VEC], types.UNIT),
            "tensor_matmul": FuncSig([types.TENSOR, types.TENSOR], types.TENSOR),
            "channel": FuncSig([], types.CHANNEL),
            "send": FuncSig([types.CHANNEL, types.INT], types.UNIT),
            "recv": FuncSig([types.CHANNEL], types.INT),
            "channel_close": FuncSig([types.CHANNEL], types.UNIT),
            "spawn": FuncSig([], types.UNIT),
        }

    def check_module(self, module: ast.Module) -> TypeInfo:
        self.module_name = module.name
        self.import_aliases = {}
        self.use_modules = []
        self.struct_defs = dict(self.external_structs)
        self.enum_defs = dict(self.external_enums)
        self.custom_types = dict(self.external_types)
        self.generic_structs = {}
        self.generic_enums = {}
        self.generic_funcs = dict(self.external_generic_funcs)
        self.specialized_functions = []
        self.impl_functions = []
        self.trait_defs = {}
        self.impl_methods = {}
        self.impl_traits = {}
        enum_names = {stmt.name for stmt in module.body if isinstance(stmt, ast.EnumDef)}
        if "Result" not in self.generic_enums and "Result" not in enum_names:
            self.generic_enums["Result"] = (
                [ast.TypeParam(name="T", bounds=[]), ast.TypeParam(name="E", bounds=[])],
                [("Ok", ast.TypeRef(name="T")), ("Err", ast.TypeRef(name="E"))],
            )
        if "Option" not in self.generic_enums and "Option" not in enum_names:
            self.generic_enums["Option"] = (
                [ast.TypeParam(name="T", bounds=[])],
                [("Some", ast.TypeRef(name="T")), ("None", None)],
            )
        for stmt in module.body:
            if isinstance(stmt, ast.Import):
                self._register_import(stmt)
        for stmt in module.body:
            if isinstance(stmt, ast.StructDef):
                self._register_struct(stmt)
            elif isinstance(stmt, ast.EnumDef):
                self._register_enum(stmt)
            elif isinstance(stmt, ast.TraitDef):
                self._register_trait(stmt)
            elif isinstance(stmt, ast.ImplDef):
                self._register_impl(stmt)
        for stmt in module.body:
            if isinstance(stmt, ast.FunctionDef):
                if stmt.type_params:
                    self.generic_funcs[stmt.name] = stmt
                    continue
                params = [self._resolve_type(p.type_ref) for p in stmt.params]
                self.func_sigs[stmt.name] = FuncSig(params=params, returns=self._resolve_type(stmt.return_type))
            elif isinstance(stmt, ast.ExternFunctionDef):
                params = [self._resolve_type(p.type_ref) for p in stmt.params]
                self.func_sigs[stmt.name] = FuncSig(params=params, returns=self._resolve_type(stmt.return_type))
        for func in self.impl_functions:
            params = [self._resolve_type(p.type_ref) for p in func.params]
            self.func_sigs[func.name] = FuncSig(params=params, returns=self._resolve_type(func.return_type))
        for stmt in module.body:
            if isinstance(stmt, ast.FunctionDef):
                if stmt.type_params:
                    continue
                self._check_function(stmt)
            elif isinstance(stmt, ast.ExternFunctionDef):
                continue
            elif isinstance(stmt, ast.TraitDef):
                continue
            elif isinstance(stmt, ast.ImplDef):
                continue
            else:
                self._check_stmt(stmt)
        for func in self.impl_functions:
            self._check_function(func)
        return TypeInfo(expr_types=self.expr_types, var_types=self.var_types)

    def _check_function(self, func: ast.FunctionDef) -> None:
        local_vars: Dict[str, types.Type] = {}
        for param in func.params:
            local_vars[param.name] = self._resolve_type(param.type_ref)
        self.current_return_type = self._resolve_type(func.return_type) if func.return_type else None
        for stmt in func.body:
            self._check_stmt(stmt, local_vars, func.return_type)
        self.current_return_type = None

    def _check_stmt(
        self,
        stmt: ast.Stmt,
        local_vars: Optional[Dict[str, types.Type]] = None,
        return_type: Optional[ast.TypeRef] = None,
    ) -> None:
        local_vars = local_vars if local_vars is not None else self.var_types
        if isinstance(stmt, ast.Assign):
            value_type = self._check_expr(stmt.value, local_vars)
            if isinstance(stmt.target, ast.Name):
                local_vars[stmt.target.value] = value_type
            elif isinstance(stmt.target, ast.MemberAccess):
                target_type = self._check_expr(stmt.target, local_vars)
                if target_type != value_type:
                    self.errors.append(self._diag(stmt, "Assignment type mismatch for field"))
            else:
                self.errors.append(self._diag(stmt, "Assignment target must be a name"))
        elif isinstance(stmt, ast.AddAssign):
            target_type = self._check_expr(stmt.target, local_vars)
            value_type = self._check_expr(stmt.value, local_vars)
            if target_type != types.INT or value_type != types.INT:
                self.errors.append(self._diag(stmt, "AddAssign requires int"))
        elif isinstance(stmt, ast.If):
            cond_type = self._check_expr(stmt.condition, local_vars)
            if cond_type != types.BOOL:
                self.errors.append(self._diag(stmt, "If condition must be bool"))
            for inner in stmt.body:
                self._check_stmt(inner, local_vars, return_type)
            if stmt.else_body:
                for inner in stmt.else_body:
                    self._check_stmt(inner, local_vars, return_type)
        elif isinstance(stmt, ast.Repeat):
            count_type = self._check_expr(stmt.count, local_vars)
            if count_type != types.INT:
                self.errors.append(self._diag(stmt, "Repeat count must be int"))
            self.loop_depth += 1
            for inner in stmt.body:
                self._check_stmt(inner, local_vars, return_type)
            self.loop_depth -= 1
        elif isinstance(stmt, ast.UnsafeBlock):
            if not stmt.reason:
                self.errors.append(self._diag(stmt, "unsafe block requires justification string"))
            for inner in stmt.body:
                self._check_stmt(inner, local_vars, return_type)
        elif isinstance(stmt, ast.While):
            cond_type = self._check_expr(stmt.condition, local_vars)
            if cond_type != types.BOOL:
                self.errors.append(self._diag(stmt, "While condition must be bool"))
            self.loop_depth += 1
            for inner in stmt.body:
                self._check_stmt(inner, local_vars, return_type)
            self.loop_depth -= 1
        elif isinstance(stmt, ast.Match):
            value_type = self._check_expr(stmt.value, local_vars)
            is_enum = value_type.name in self.enum_defs or value_type.name in self.external_enums
            is_struct = value_type.name in self.struct_defs or value_type.name in self.external_structs
            if value_type not in (types.INT, types.BOOL) and not is_enum and not is_struct:
                self.errors.append(self._diag(stmt, "match supports int/bool/enum/struct only"))
            for case in stmt.cases:
                case_locals = dict(local_vars)
                if is_enum:
                    case_locals = self._check_enum_pattern(case.pattern, value_type, case_locals, case)
                elif is_struct:
                    case_locals = self._check_struct_pattern(case.pattern, value_type, case_locals, case)
                else:
                    if isinstance(case.pattern, ast.LiteralPattern):
                        case_type = self._check_expr(case.pattern.value, local_vars)
                        if case_type != value_type:
                            self.errors.append(self._diag(case, "match case type must match"))
                    elif isinstance(case.pattern, ast.WildcardPattern):
                        pass
                    elif isinstance(case.pattern, ast.BindPattern):
                        case_locals[case.pattern.name] = value_type
                    else:
                        self.errors.append(self._diag(case, "match case must be literal or '_'"))
                if case.guard:
                    guard_type = self._check_expr(case.guard, case_locals)
                    if guard_type != types.BOOL:
                        self.errors.append(self._diag(case, "match guard must be bool"))
                for inner in case.body:
                    self._check_stmt(inner, case_locals, return_type)
            if stmt.else_body:
                for inner in stmt.else_body:
                    self._check_stmt(inner, local_vars, return_type)
        elif isinstance(stmt, ast.StructDef):
            return
        elif isinstance(stmt, ast.EnumDef):
            return
        elif isinstance(stmt, ast.Print):
            self._check_expr(stmt.value, local_vars)
        elif isinstance(stmt, ast.Return):
            if return_type is None:
                return
            expected = self._resolve_type(return_type)
            if stmt.value is None:
                if expected != types.UNIT:
                    self.errors.append(self._diag(stmt, "Return value required"))
            else:
                actual = self._check_expr(stmt.value, local_vars)
                if actual != expected and not self._is_panic_expr(stmt.value):
                    self.errors.append(self._diag(stmt, f"Return type mismatch: {actual} != {expected}"))
        elif isinstance(stmt, ast.Break):
            if self.loop_depth == 0:
                self.errors.append(self._diag(stmt, "break used outside loop"))
        elif isinstance(stmt, ast.Continue):
            if self.loop_depth == 0:
                self.errors.append(self._diag(stmt, "continue used outside loop"))
        elif isinstance(stmt, ast.BufferCreate):
            size_type = self._check_expr(stmt.size, local_vars)
            if size_type != types.INT:
                self.errors.append(self._diag(stmt, "Buffer size must be int"))
            local_vars[stmt.name] = types.BUFFER
        elif isinstance(stmt, ast.BorrowSlice):
            buffer_type = self._check_expr(stmt.buffer, local_vars)
            if buffer_type != types.BUFFER:
                self.errors.append(self._diag(stmt, "BorrowSlice requires buffer"))
            self._check_expr(stmt.start, local_vars)
            self._check_expr(stmt.end, local_vars)
            local_vars[stmt.name] = types.VIEW
        elif isinstance(stmt, ast.Move):
            self._check_expr(stmt.src, local_vars)
            if stmt.dst in local_vars:
                self.errors.append(self._diag(stmt, "Move destination already defined"))
            local_vars[stmt.dst] = self._check_expr(stmt.src, local_vars)
        elif isinstance(stmt, ast.Release):
            target_type = self._check_expr(stmt.target, local_vars)
            if target_type not in (types.BUFFER, types.TENSOR, types.CHANNEL, types.STRING, types.VEC):
                self.errors.append(self._diag(stmt, "Release requires buffer/tensor/channel/string/vec"))
        elif isinstance(stmt, ast.FunctionDef):
            self._check_function(stmt)
        elif isinstance(stmt, ast.ExternFunctionDef):
            return
        elif isinstance(stmt, ast.Import):
            return
        else:
            self.errors.append(diagnostics.Diagnostic("Unsupported statement"))

    def _check_expr(self, expr: ast.Expr, local_vars: Dict[str, types.Type]) -> types.Type:
        if isinstance(expr, ast.IntLit):
            self.expr_types[id(expr)] = types.INT
            return types.INT
        if isinstance(expr, ast.StringLit):
            self.expr_types[id(expr)] = types.STRING
            return types.STRING
        if isinstance(expr, ast.BoolLit):
            self.expr_types[id(expr)] = types.BOOL
            return types.BOOL
        if isinstance(expr, ast.Name):
            if expr.value not in local_vars:
                self.errors.append(self._diag(expr, f"Undefined name: {expr.value}"))
                local_vars[expr.value] = types.UNIT
            self.expr_types[id(expr)] = local_vars[expr.value]
            return local_vars[expr.value]
        if isinstance(expr, ast.MemberAccess):
            base_type = self._check_expr(expr.value, local_vars)
            struct_fields = self.struct_defs.get(base_type.name)
            if struct_fields is None:
                self.errors.append(self._diag(expr, "Field access requires struct type"))
                self.expr_types[id(expr)] = types.UNIT
                return types.UNIT
            for field_name, field_type in struct_fields:
                if field_name == expr.name:
                    self.expr_types[id(expr)] = field_type
                    return field_type
            self.errors.append(self._diag(expr, f"Unknown field: {expr.name}"))
            self.expr_types[id(expr)] = types.UNIT
            return types.UNIT
        if isinstance(expr, ast.BorrowExpr):
            target_type = self._check_expr(expr.value, local_vars)
            if target_type not in (types.BUFFER, types.VIEW):
                self.errors.append(self._diag(expr, "Borrowing requires buffer/view"))
            self.expr_types[id(expr)] = types.VIEW
            return types.VIEW
        if isinstance(expr, ast.CopyExpr):
            target_type = self._check_expr(expr.value, local_vars)
            if not target_type.is_copy:
                self.errors.append(self._diag(expr, "Copy requires Copy type"))
            self.expr_types[id(expr)] = target_type
            return target_type
        if isinstance(expr, ast.UnaryOp):
            value_type = self._check_expr(expr.value, local_vars)
            if value_type != types.INT:
                self.errors.append(self._diag(expr, "Unary arithmetic requires int"))
            self.expr_types[id(expr)] = types.INT
            return types.INT
        if isinstance(expr, ast.LogicalOp):
            left_type = self._check_expr(expr.left, local_vars)
            right_type = self._check_expr(expr.right, local_vars)
            if left_type != types.BOOL or right_type != types.BOOL:
                self.errors.append(self._diag(expr, "Logical operands must be bool"))
            self.expr_types[id(expr)] = types.BOOL
            return types.BOOL
        if isinstance(expr, ast.TryExpr):
            inner_type = self._check_expr(expr.value, local_vars)
            ok_type = self._check_try_expr(expr, inner_type)
            self.expr_types[id(expr)] = ok_type
            return ok_type
        if isinstance(expr, ast.BinOp):
            left = self._check_expr(expr.left, local_vars)
            right = self._check_expr(expr.right, local_vars)
            if left != types.INT or right != types.INT:
                self.errors.append(self._diag(expr, "Arithmetic operands must be int"))
            self.expr_types[id(expr)] = types.INT
            return types.INT
        if isinstance(expr, ast.Call):
            return self._check_call(expr, local_vars)
        self.errors.append(self._diag(expr, "Unknown expression"))
        self.expr_types[id(expr)] = types.UNIT
        return types.UNIT

    def _diag(self, node: object, message: str) -> diagnostics.Diagnostic:
        span = getattr(node, "span", None)
        return diagnostics.Diagnostic(message=message, span=span)

    def _split_specialized_name(self, name: str) -> tuple[str, List[str]]:
        parts = name.split("__")
        return parts[0], parts[1:]

    def _check_type_param_bounds(self, param: ast.TypeParam, actual: types.Type, ctx: object) -> None:
        if not param.bounds:
            return
        implemented = self.impl_traits.get(actual.name, set())
        for bound in param.bounds:
            if bound not in implemented:
                hint = f"hint: implement `impl {bound} for {actual.name}`"
                if bound in self.trait_defs:
                    available = self._trait_impl_hint(bound)
                    suffix = f"; {available}" if available else ""
                    self.errors.append(self._diag(ctx, f"type '{actual.name}' does not implement trait '{bound}' ({hint}{suffix})"))
                else:
                    self.errors.append(self._diag(ctx, f"type '{actual.name}' does not implement trait '{bound}' ({hint}; trait not found)"))

    def _check_try_expr(self, expr: ast.TryExpr, inner_type: types.Type) -> types.Type:
        base, args = self._split_specialized_name(inner_type.name)
        if base not in ("Result", "Option"):
            self.errors.append(self._diag(expr, "try requires Result or Option"))
            return types.UNIT
        if self.current_return_type is None:
            self.errors.append(self._diag(expr, "try used outside of function"))
            return types.UNIT
        ret_base, ret_args = self._split_specialized_name(self.current_return_type.name)
        if ret_base != base:
            self.errors.append(self._diag(expr, "try requires matching return type"))
            return types.UNIT
        if base == "Result":
            if len(args) < 2 or len(ret_args) < 2:
                self.errors.append(self._diag(expr, "Result must have two type arguments"))
                return types.UNIT
            if args[1] != ret_args[1]:
                self.errors.append(self._diag(expr, "try requires matching Result error type"))
                return types.UNIT
            return self._resolve_type(ast.TypeRef(name=args[0]))
        if base == "Option":
            if not args or not ret_args:
                self.errors.append(self._diag(expr, "Option must have one type argument"))
                return types.UNIT
            return self._resolve_type(ast.TypeRef(name=args[0]))
        return types.UNIT

    def _check_enum_pattern(
        self,
        pattern: ast.Pattern,
        expected_type: types.Type,
        local_vars: Dict[str, types.Type],
        ctx: object,
    ) -> Dict[str, types.Type]:
        if isinstance(pattern, ast.WildcardPattern):
            return local_vars
        if not isinstance(pattern, ast.EnumPattern):
            self.errors.append(self._diag(ctx, "enum match requires enum case pattern"))
            return local_vars
        enum_name = pattern.enum_name
        expected_name = expected_type.name
        expected_base = expected_name.split("__")[0]
        if enum_name != expected_name and enum_name == expected_base:
            enum_name = expected_name
            pattern.enum_name = expected_name
        if enum_name != expected_name:
            self.errors.append(self._diag(ctx, "match enum case must match value type"))
            return local_vars
        enum_cases = self.enum_defs.get(enum_name) or self.external_enums.get(enum_name)
        if not enum_cases:
            self.errors.append(self._diag(ctx, f"Unknown enum: {enum_name}"))
            return local_vars
        found = next((c for c in enum_cases if c[0] == pattern.case_name), None)
        if not found:
            self.errors.append(self._diag(ctx, f"Unknown enum case: {pattern.case_name}"))
            return local_vars
        payload_type = found[1]
        if pattern.binding and pattern.payload:
            self.errors.append(self._diag(ctx, "enum case cannot bind and match payload"))
            return local_vars
        if pattern.binding:
            if payload_type is None:
                self.errors.append(self._diag(ctx, "enum case has no payload to bind"))
                return local_vars
            local_vars[pattern.binding] = payload_type
            return local_vars
        if pattern.payload:
            if payload_type is None:
                self.errors.append(self._diag(ctx, "enum case has no payload to match"))
                return local_vars
            return self._check_pattern(pattern.payload, payload_type, local_vars, ctx)
        return local_vars

    def _check_struct_pattern(
        self,
        pattern: ast.Pattern,
        expected_type: types.Type,
        local_vars: Dict[str, types.Type],
        ctx: object,
    ) -> Dict[str, types.Type]:
        if isinstance(pattern, ast.WildcardPattern):
            return local_vars
        if isinstance(pattern, ast.BindPattern):
            local_vars[pattern.name] = expected_type
            return local_vars
        if not isinstance(pattern, ast.StructPattern):
            self.errors.append(self._diag(ctx, "struct match requires struct pattern"))
            return local_vars
        if pattern.struct_name != expected_type.name:
            self.errors.append(self._diag(ctx, "match struct pattern must match value type"))
            return local_vars
        fields = self.struct_defs.get(pattern.struct_name) or self.external_structs.get(pattern.struct_name)
        if not fields:
            self.errors.append(self._diag(ctx, f"Unknown struct: {pattern.struct_name}"))
            return local_vars
        if len(pattern.fields) != len(fields):
            self.errors.append(
                self._diag(ctx, f"struct pattern field count mismatch: expected {len(fields)}, got {len(pattern.fields)}")
            )
            return local_vars
        for idx, field_pat in enumerate(pattern.fields):
            field_type = fields[idx][1]
            local_vars = self._check_pattern(field_pat, field_type, local_vars, ctx)
        return local_vars

    def _check_pattern(
        self,
        pattern: ast.Pattern,
        expected_type: types.Type,
        local_vars: Dict[str, types.Type],
        ctx: object,
    ) -> Dict[str, types.Type]:
        if isinstance(pattern, ast.WildcardPattern):
            return local_vars
        if isinstance(pattern, ast.BindPattern):
            local_vars[pattern.name] = expected_type
            return local_vars
        if isinstance(pattern, ast.LiteralPattern):
            case_type = self._check_expr(pattern.value, local_vars)
            if case_type != expected_type:
                self.errors.append(self._diag(ctx, "match case type must match"))
            return local_vars
        if isinstance(pattern, ast.StructPattern):
            return self._check_struct_pattern(pattern, expected_type, local_vars, ctx)
        if isinstance(pattern, ast.EnumPattern):
            return self._check_enum_pattern(pattern, expected_type, local_vars, ctx)
        self.errors.append(self._diag(ctx, "Unsupported pattern"))
        return local_vars

    def _check_call(self, expr: ast.Call, local_vars: Dict[str, types.Type]) -> types.Type:
        callee = self._resolve_callee(expr)
        if callee not in self.func_sigs and "__" in callee:
            self._ensure_function_specialization_from_name(callee)
        if "." in callee:
            prefix, method_name = callee.split(".", 1)
            if prefix in local_vars:
                recv_type = local_vars[prefix]
                methods = self.impl_methods.get(recv_type.name, {})
                if method_name in methods:
                    impl_name, sig = methods[method_name]
                    expr.callee = impl_name
                    expr.args = [ast.Name(value=prefix, span=expr.span)] + expr.args
                    callee = impl_name
        if callee not in self.struct_defs and "__" in callee:
            self._ensure_specialization_from_name(callee)
        if callee in self.struct_defs:
            fields = self.struct_defs[callee]
            if len(expr.args) != len(fields):
                self.errors.append(self._diag(expr, f"Struct argument count mismatch: expected {len(fields)}, got {len(expr.args)}"))
            for idx, arg in enumerate(expr.args):
                arg_type = self._check_expr(arg, local_vars)
                if idx < len(fields) and arg_type != fields[idx][1]:
                    self.errors.append(self._diag(expr, f"Struct field type mismatch at {idx}: {arg_type} != {fields[idx][1]}"))
            t = self.custom_types.get(callee, types.Type(name=callee, is_copy=False))
            self.expr_types[id(expr)] = t
            return t
        if "." in callee:
            enum_name, case_name = callee.split(".", 1)
            if enum_name not in self.enum_defs and "__" in enum_name:
                self._ensure_specialization_from_name(enum_name)
            if enum_name in self.enum_defs:
                cases = self.enum_defs[enum_name]
                case = next((c for c in cases if c[0] == case_name), None)
                if case is None:
                    self.errors.append(self._diag(expr, f"Unknown enum case: {case_name}"))
                    self.expr_types[id(expr)] = types.UNIT
                    return types.UNIT
                payload_type = case[1]
                if payload_type is None and expr.args:
                    self.errors.append(self._diag(expr, "Enum case takes no payload"))
                if payload_type is not None:
                    if len(expr.args) != 1:
                        self.errors.append(self._diag(expr, "Enum case requires one payload value"))
                    else:
                        arg_type = self._check_expr(expr.args[0], local_vars)
                        if arg_type != payload_type:
                            self.errors.append(self._diag(expr, f"Enum payload type mismatch: {arg_type} != {payload_type}"))
                t = self.custom_types.get(enum_name, types.Type(name=enum_name, is_copy=False))
                self.expr_types[id(expr)] = t
                return t
            if enum_name in self.generic_enums:
                t = self._specialize_generic_enum_case(enum_name, case_name, expr, local_vars)
                self.expr_types[id(expr)] = t
                return t
        if callee in ("gt", "lt", "eq", "ge", "le", "ne"):
            if len(expr.args) != 2:
                self.errors.append(self._diag(expr, "Comparison requires two arguments"))
                self.expr_types[id(expr)] = types.BOOL
                return types.BOOL
            left = self._check_expr(expr.args[0], local_vars)
            right = self._check_expr(expr.args[1], local_vars)
            if left != right:
                self.errors.append(self._diag(expr, "Comparison operands must match"))
            self.expr_types[id(expr)] = types.BOOL
            return types.BOOL
        sig = self.builtin_sigs.get(callee) or self.func_sigs.get(callee) or self.external_sigs.get(callee)
        if sig is None:
            for arg in expr.args:
                self._check_expr(arg, local_vars)
            self.errors.append(self._diag(expr, f"Unknown function: {callee}"))
            self.expr_types[id(expr)] = types.UNIT
            return types.UNIT
        if callee == "spawn":
            if len(expr.args) not in (1, 2):
                self.errors.append(self._diag(expr, "spawn requires 1 or 2 arguments"))
            if len(expr.args) >= 1:
                self._check_expr(expr.args[0], local_vars)
            if len(expr.args) == 2:
                arg_type = self._check_expr(expr.args[1], local_vars)
                if arg_type != types.CHANNEL:
                    self.errors.append(self._diag(expr, "spawn channel argument must be channel"))
            self.expr_types[id(expr)] = types.UNIT
            return types.UNIT
        if len(expr.args) != len(sig.params):
            self.errors.append(self._diag(expr, f"Argument count mismatch: expected {len(sig.params)}, got {len(expr.args)}"))
        for idx, arg in enumerate(expr.args):
            arg_type = self._check_expr(arg, local_vars)
            if idx < len(sig.params) and arg_type != sig.params[idx]:
                self.errors.append(self._diag(expr, f"Argument type mismatch at {idx}: {arg_type} != {sig.params[idx]}"))
        self.expr_types[id(expr)] = sig.returns
        return sig.returns

    def _specialize_generic_enum_case(
        self,
        enum_name: str,
        case_name: str,
        expr: ast.Call,
        local_vars: Dict[str, types.Type],
    ) -> types.Type:
        params, cases = self.generic_enums[enum_name]
        case = next((c for c in cases if c[0] == case_name), None)
        if case is None:
            self.errors.append(self._diag(expr, f"Unknown enum case: {case_name}"))
            return types.UNIT
        payload_ref = case[1]
        param_names = [p.name for p in params]
        mapping: Dict[str, types.Type] = {}
        if payload_ref is None:
            if expr.args:
                self.errors.append(self._diag(expr, "Enum case takes no payload"))
        else:
            if len(expr.args) != 1:
                self.errors.append(self._diag(expr, "Enum case requires one payload value"))
            else:
                arg_type = self._check_expr(expr.args[0], local_vars)
                if payload_ref.name in param_names and not payload_ref.args:
                    mapping[payload_ref.name] = arg_type
                else:
                    expected = self._resolve_type_ref_subst(payload_ref, mapping)
                    if arg_type != expected:
                        self.errors.append(self._diag(expr, f"Enum payload type mismatch: {arg_type} != {expected}"))
        if self.current_return_type:
            ret_base, ret_args = self._split_specialized_name(self.current_return_type.name)
            if ret_base == enum_name and len(ret_args) == len(param_names):
                for name, arg in zip(param_names, ret_args):
                    if name not in mapping:
                        mapping[name] = self._resolve_type(ast.TypeRef(name=arg))
        if len(mapping) != len(param_names):
            missing = [name for name in param_names if name not in mapping]
            if missing:
                self.errors.append(self._diag(expr, f"Cannot infer type parameters: {', '.join(missing)}"))
        arg_types = [mapping.get(name, types.UNIT) for name in param_names]
        spec_ref = ast.TypeRef(name=enum_name, args=[ast.TypeRef(name=t.name) for t in arg_types])
        spec_type = self._resolve_generic_type_ref(spec_ref)
        expr.callee = f"{spec_type.name}.{case_name}"
        spec_cases = self.enum_defs.get(spec_type.name)
        if spec_cases:
            spec_case = next((c for c in spec_cases if c[0] == case_name), None)
            if spec_case:
                payload_type = spec_case[1]
                if payload_type is None and expr.args:
                    self.errors.append(self._diag(expr, "Enum case takes no payload"))
                if payload_type is not None and len(expr.args) == 1:
                    arg_type = self._check_expr(expr.args[0], local_vars)
                    if arg_type != payload_type:
                        self.errors.append(self._diag(expr, f"Enum payload type mismatch: {arg_type} != {payload_type}"))
        return spec_type

    def _register_struct(self, stmt: ast.StructDef) -> None:
        if stmt.type_params:
            if stmt.name in self.generic_structs:
                self.errors.append(self._diag(stmt, f"Duplicate generic struct: {stmt.name}"))
            else:
                fields = [(field.name, field.type_ref) for field in stmt.fields]
                self.generic_structs[stmt.name] = (stmt.type_params, fields)
            return
        fields: List[tuple[str, types.Type]] = []
        is_copy = True
        for field in stmt.fields:
            t = self._resolve_type(field.type_ref)
            fields.append((field.name, t))
            if not t.is_copy:
                is_copy = False
        self.struct_defs[stmt.name] = fields
        self.custom_types[stmt.name] = types.Type(name=stmt.name, is_copy=is_copy)

    def _register_enum(self, stmt: ast.EnumDef) -> None:
        if stmt.type_params:
            if stmt.name in self.generic_enums:
                self.errors.append(self._diag(stmt, f"Duplicate generic enum: {stmt.name}"))
            else:
                cases: List[tuple[str, Optional[ast.TypeRef]]] = []
                for case in stmt.cases:
                    cases.append((case.name, case.payload))
                self.generic_enums[stmt.name] = (stmt.type_params, cases)
            return
        cases: List[tuple[str, Optional[types.Type]]] = []
        for case in stmt.cases:
            payload = self._resolve_type(case.payload) if case.payload else None
            cases.append((case.name, payload))
        self.enum_defs[stmt.name] = cases
        self.custom_types[stmt.name] = types.Type(name=stmt.name, is_copy=False)

    def _register_trait(self, stmt: ast.TraitDef) -> None:
        if stmt.name in self.trait_defs:
            self.errors.append(self._diag(stmt, f"Duplicate trait: {stmt.name}"))
            return
        methods: Dict[str, FuncSig] = {}
        for method in stmt.methods:
            params = [self._resolve_type(p.type_ref) for p in method.params]
            methods[method.name] = FuncSig(params=params, returns=self._resolve_type(method.return_type))
        self.trait_defs[stmt.name] = (stmt.type_params, methods)

    def _register_impl(self, stmt: ast.ImplDef) -> None:
        type_name = stmt.for_type.name
        if stmt.trait_name:
            self.impl_traits.setdefault(type_name, set()).add(stmt.trait_name)
        impl_methods = self.impl_methods.setdefault(type_name, {})
        for method in stmt.methods:
            impl_name = self._impl_method_name(type_name, stmt.trait_name, method.name)
            params = [self._substitute_self_type(p.type_ref, stmt.for_type) for p in method.params]
            return_type = self._substitute_self_type(method.return_type, stmt.for_type)
            impl_func = ast.FunctionDef(
                name=impl_name,
                type_params=[],
                params=[ast.Param(name=p.name, type_ref=p.type_ref) for p in method.params],
                return_type=return_type,
                body=method.body,
                is_public=False,
                span=method.span,
            )
            for param in impl_func.params:
                param.type_ref = self._substitute_self_type(param.type_ref, stmt.for_type)
            sig = FuncSig(params=[self._resolve_type(p.type_ref) for p in impl_func.params], returns=self._resolve_type(return_type))
            impl_methods[method.name] = (impl_name, sig)
            self.impl_functions.append(impl_func)

    def _impl_method_name(self, type_name: str, trait_name: Optional[str], method_name: str) -> str:
        if trait_name:
            return f"{type_name}__{trait_name}__{method_name}"
        return f"{type_name}__{method_name}"

    def _substitute_self_type(self, tref: ast.TypeRef, for_type: ast.TypeRef) -> ast.TypeRef:
        if tref.name == "Self":
            return ast.TypeRef(name=for_type.name, args=for_type.args or [])
        if not tref.args:
            return tref
        return ast.TypeRef(name=tref.name, args=[self._substitute_self_type(arg, for_type) for arg in tref.args])

    def _register_import(self, stmt: ast.Import) -> None:
        module = stmt.module
        if stmt.alias:
            if stmt.alias in self.import_aliases:
                self.errors.append(self._diag(stmt, f"Duplicate import alias: {stmt.alias}"))
            else:
                self.import_aliases[stmt.alias] = module
        else:
            self.import_aliases[module] = module
        if stmt.is_use:
            if module not in self.use_modules:
                self.use_modules.append(module)

    def _resolve_callee(self, expr: ast.Call) -> str:
        callee = expr.callee
        if "." in callee:
            prefix, fn_name = callee.split(".", 1)
            if prefix in self.import_aliases:
                callee = f"{self.import_aliases[prefix]}.{fn_name}"
                expr.callee = callee
            if "__" in fn_name:
                base = fn_name.split("__")[0]
                if f"{prefix}.{base}" in self.external_generic_funcs:
                    callee = f"{prefix}__{fn_name}"
                    expr.callee = callee
            return callee
        if callee in self.builtin_sigs or callee in self.func_sigs:
            return callee
        if callee in self.external_sigs:
            return callee
        candidates = [f"{module}.{callee}" for module in self.use_modules if f"{module}.{callee}" in self.external_sigs]
        if len(candidates) == 1:
            expr.callee = candidates[0]
            return candidates[0]
        if len(candidates) > 1:
            self.errors.append(self._diag(expr, f"Ambiguous call '{callee}' from use imports"))
        if "__" in callee:
            base = callee.split("__")[0]
            gen_candidates = [
                f"{module}__{callee}"
                for module in self.use_modules
                if f"{module}.{base}" in self.external_generic_funcs
            ]
            if len(gen_candidates) == 1:
                expr.callee = gen_candidates[0]
                return gen_candidates[0]
            if len(gen_candidates) > 1:
                self.errors.append(self._diag(expr, f"Ambiguous generic call '{callee}' from use imports"))
        return callee

    def _resolve_type(self, tref: ast.TypeRef) -> types.Type:
        name = tref.name
        if tref.args:
            return self._resolve_generic_type_ref(tref)
        if name in self.custom_types:
            return self.custom_types[name]
        external = self._resolve_external_type(name)
        if external is not None:
            return external
        if name in ("int", "정수"):
            return types.INT
        if name in ("bool", "불리언"):
            return types.BOOL
        if name in ("string", "문자열"):
            return types.STRING
        if name in ("buffer", "버퍼"):
            return types.BUFFER
        if name in ("view", "뷰"):
            return types.VIEW
        if name in ("tensor", "텐서"):
            return types.TENSOR
        if name in ("channel", "채널"):
            return types.CHANNEL
        if name in ("vec", "벡터"):
            return types.VEC
        if name in ("unit", "void", "없음"):
            return types.UNIT
        return types.Type(name=name, is_copy=False)

    def _resolve_generic_type_ref(self, tref: ast.TypeRef) -> types.Type:
        name = tref.name
        args = tref.args or []
        if name in self.generic_structs:
            params, fields = self.generic_structs[name]
            param_names = [p.name for p in params]
            if len(args) != len(param_names):
                self.errors.append(diagnostics.Diagnostic(f"Generic struct {name} expects {len(param_names)} args, got {len(args)}"))
                return types.Type(name=name, is_copy=False)
            arg_types = [self._resolve_type(arg) for arg in args]
            for param, arg_type in zip(params, arg_types):
                self._check_type_param_bounds(param, arg_type, tref)
            subst = dict(zip(param_names, arg_types))
            spec_name = self._specialize_name(name, arg_types)
            if spec_name not in self.custom_types:
                spec_fields: List[tuple[str, types.Type]] = []
                is_copy = True
                for field_name, field_tref in fields:
                    spec_type = self._resolve_type_ref_subst(field_tref, subst)
                    spec_fields.append((field_name, spec_type))
                    if not spec_type.is_copy:
                        is_copy = False
                self.struct_defs[spec_name] = spec_fields
                self.custom_types[spec_name] = types.Type(name=spec_name, is_copy=is_copy)
            tref.name = spec_name
            tref.args = []
            return self.custom_types[spec_name]
        if name in self.generic_enums:
            params, cases = self.generic_enums[name]
            param_names = [p.name for p in params]
            if len(args) != len(param_names):
                self.errors.append(diagnostics.Diagnostic(f"Generic enum {name} expects {len(param_names)} args, got {len(args)}"))
                return types.Type(name=name, is_copy=False)
            arg_types = [self._resolve_type(arg) for arg in args]
            for param, arg_type in zip(params, arg_types):
                self._check_type_param_bounds(param, arg_type, tref)
            subst = dict(zip(param_names, arg_types))
            spec_name = self._specialize_name(name, arg_types)
            if spec_name not in self.custom_types:
                spec_cases: List[tuple[str, Optional[types.Type]]] = []
                for case_name, payload in cases:
                    spec_payload = self._resolve_type_ref_subst(payload, subst) if payload else None
                    spec_cases.append((case_name, spec_payload))
                self.enum_defs[spec_name] = spec_cases
                self.custom_types[spec_name] = types.Type(name=spec_name, is_copy=False)
            tref.name = spec_name
            tref.args = []
            return self.custom_types[spec_name]
        self.errors.append(diagnostics.Diagnostic(f"Unknown generic type: {name}"))
        return types.Type(name=name, is_copy=False)

    def _resolve_type_ref_subst(self, tref: ast.TypeRef, subst: Dict[str, types.Type]) -> types.Type:
        if tref.name in subst:
            return subst[tref.name]
        if tref.args:
            return self._resolve_generic_type_ref(tref)
        return self._resolve_type(tref)

    def _specialize_name(self, base: str, args: List[types.Type]) -> str:
        suffix = "__".join(arg.name.replace(".", "__") for arg in args)
        return f"{base}__{suffix}"

    def _ensure_specialization_from_name(self, name: str) -> None:
        parts = name.split("__")
        if len(parts) < 2:
            return
        base = parts[0]
        if base not in self.generic_structs and base not in self.generic_enums:
            return
        arg_refs = [ast.TypeRef(name=part) for part in parts[1:]]
        tref = ast.TypeRef(name=base, args=arg_refs)
        self._resolve_generic_type_ref(tref)

    def _ensure_function_specialization_from_name(self, name: str) -> None:
        parts = name.split("__")
        if len(parts) < 2:
            return
        base = parts[0]
        type_parts = parts[1:]
        if base not in self.generic_funcs:
            if len(parts) < 3:
                return
            dotted = f"{parts[0]}.{parts[1]}"
            if dotted not in self.generic_funcs:
                return
            base = dotted
            type_parts = parts[2:]
        func = self.generic_funcs[base]
        param_names = [p.name for p in func.type_params]
        if len(type_parts) != len(param_names):
            self.errors.append(diagnostics.Diagnostic(f"Generic function {base} expects {len(param_names)} args, got {len(type_parts)}"))
            return
        arg_types = [self._resolve_type(ast.TypeRef(name=part)) for part in type_parts]
        for param, arg_type in zip(func.type_params, arg_types):
            self._check_type_param_bounds(param, arg_type, func)
        subst = dict(zip(param_names, arg_types))
        spec_name = name
        if spec_name in self.func_sigs:
            return
        spec_params = [ast.Param(name=p.name, type_ref=self._substitute_type_params(p.type_ref, subst)) for p in func.params]
        spec_return = self._substitute_type_params(func.return_type, subst)
        spec_params = [ast.Param(name=p.name, type_ref=self._finalize_type_ref(p.type_ref)) for p in spec_params]
        spec_return = self._finalize_type_ref(spec_return)
        spec_func = ast.FunctionDef(
            name=spec_name,
            type_params=[],
            params=spec_params,
            return_type=spec_return,
            body=func.body,
            is_public=func.is_public,
            span=func.span,
        )
        self.specialized_functions.append(spec_func)
        self.func_sigs[spec_name] = FuncSig(
            params=[self._resolve_type(p.type_ref) for p in spec_params],
            returns=self._resolve_type(spec_return),
        )
        self._check_function(spec_func)

    def _substitute_type_params(self, tref: ast.TypeRef, subst: Dict[str, types.Type]) -> ast.TypeRef:
        if tref.name in subst:
            return ast.TypeRef(name=subst[tref.name].name, args=[])
        if not tref.args:
            return tref
        return ast.TypeRef(name=tref.name, args=[self._substitute_type_params(arg, subst) for arg in tref.args])

    def _finalize_type_ref(self, tref: ast.TypeRef) -> ast.TypeRef:
        resolved = self._resolve_type(tref)
        return ast.TypeRef(name=resolved.name, args=[])

    def _trait_impl_hint(self, trait_name: str) -> str:
        types_with_impl = [name for name, traits in self.impl_traits.items() if trait_name in traits]
        if not types_with_impl:
            return "no known impls in current modules"
        preview = ", ".join(sorted(types_with_impl)[:3])
        more = "..." if len(types_with_impl) > 3 else ""
        return f"known impls: {preview}{more}"

    def _is_panic_expr(self, expr: ast.Expr) -> bool:
        if isinstance(expr, ast.Call):
            return expr.callee == "panic"
        return False

    def _resolve_external_type(self, name: str) -> Optional[types.Type]:
        if not self.external_types:
            return None
        imported = set(self.import_aliases.values())
        matches = []
        for full_name, t in self.external_types.items():
            if "." not in full_name:
                continue
            mod, type_name = full_name.split(".", 1)
            if type_name == name and mod in imported:
                matches.append(t)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            self.errors.append(diagnostics.Diagnostic(f"Ambiguous type name: {name}"))
        return None


