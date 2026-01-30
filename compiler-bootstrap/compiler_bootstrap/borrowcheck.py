from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from compiler_core import ast, diagnostics, types
from compiler_bootstrap.region_infer import RegionInfer


@dataclass
class BorrowInfo:
    owner: str
    mutable: bool
    var_name: str


class BorrowChecker:
    def __init__(self, type_info: "TypeInfo") -> None:
        self.errors: List[diagnostics.Diagnostic] = []
        self.type_info = type_info
        self.active_borrows: Dict[str, List[BorrowInfo]] = {}
        self.scope_stack: List[List[BorrowInfo]] = []
        self.moved: Dict[str, bool] = {}
        self.moved_at: Dict[str, diagnostics.Span] = {}
        self.unsafe_stack: List[bool] = []
        self.current_function: Optional[str] = None
        self.stmt_node: Dict[int, int] = {}
        self.live_in: Dict[int, Set[str]] = {}
        self.live_out: Dict[int, Set[str]] = {}
        self.borrow_var_owner: Dict[str, str] = {}
        self.borrow_var_mutable: Dict[str, bool] = {}

    def check_module(self, module: ast.Module) -> None:
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
                self._check_stmt(stmt, self.type_info.var_types.copy())

    def _check_function(self, func: ast.FunctionDef) -> None:
        local_vars: Dict[str, types.Type] = {}
        for param in func.params:
            local_vars[param.name] = self._resolve_type(param.type_ref)
        self.active_borrows = {}
        self.scope_stack = [[]]
        self.moved = {}
        self.moved_at = {}
        self.unsafe_stack = [False]
        self.current_function = func.name
        region_info = RegionInfer().infer(func)
        for err in region_info.errors:
            self.errors.append(self._diag(func, f"Region inference error: {err}"))
        self._analyze_cfg(func.body)
        for stmt in func.body:
            self._check_stmt(stmt, local_vars)
        self.current_function = None

    def _check_stmt(self, stmt: ast.Stmt, local_vars: Dict[str, types.Type]) -> None:
        self._prune_dead_borrows(stmt)
        if isinstance(stmt, ast.Assign):
            if isinstance(stmt.target, ast.Name) and isinstance(stmt.value, ast.BorrowExpr):
                owner_name = self._extract_name(stmt.value.value)
                if owner_name:
                    self._register_borrow(owner_name, stmt.value.mutable, stmt.target.value, stmt)
            value_owner = self._check_expr(stmt.value, local_vars)
            if isinstance(stmt.target, ast.Name):
                local_vars[stmt.target.value] = value_owner
                if stmt.target.value in self.moved:
                    self.moved[stmt.target.value] = False
            if isinstance(stmt.value, ast.Name):
                self._move_if_needed(stmt.value.value, local_vars, stmt, stmt.value.span)
        elif isinstance(stmt, ast.AddAssign):
            self._check_expr(stmt.target, local_vars, allow_move=False)
            self._check_expr(stmt.value, local_vars)
        elif isinstance(stmt, ast.If):
            self._check_expr(stmt.condition, local_vars)
            self._enter_scope()
            for inner in stmt.body:
                self._check_stmt(inner, local_vars)
            self._exit_scope()
            if stmt.else_body:
                self._enter_scope()
                for inner in stmt.else_body:
                    self._check_stmt(inner, local_vars)
                self._exit_scope()
        elif isinstance(stmt, ast.Repeat):
            self._check_expr(stmt.count, local_vars)
            self._enter_scope()
            for inner in stmt.body:
                self._check_stmt(inner, local_vars)
            self._exit_scope()
        elif isinstance(stmt, ast.While):
            self._check_expr(stmt.condition, local_vars)
            self._enter_scope()
            for inner in stmt.body:
                self._check_stmt(inner, local_vars)
            self._exit_scope()
        elif isinstance(stmt, ast.Match):
            self._check_expr(stmt.value, local_vars)
            for case in stmt.cases:
                self._enter_scope()
                if isinstance(case.pattern, ast.LiteralPattern):
                    self._check_expr(case.pattern.value, local_vars)
                elif isinstance(case.pattern, ast.EnumPattern):
                    self._check_pattern_exprs(case.pattern, local_vars)
                elif isinstance(case.pattern, ast.StructPattern):
                    self._check_pattern_exprs(case.pattern, local_vars)
                if case.guard:
                    self._check_expr(case.guard, local_vars)
                for inner in case.body:
                    self._check_stmt(inner, local_vars)
                self._exit_scope()
            if stmt.else_body:
                self._enter_scope()
                for inner in stmt.else_body:
                    self._check_stmt(inner, local_vars)
                self._exit_scope()
        elif isinstance(stmt, ast.UnsafeBlock):
            self.unsafe_stack.append(True)
            self._enter_scope()
            for inner in stmt.body:
                self._check_stmt(inner, local_vars)
            self._exit_scope()
            self.unsafe_stack.pop()
        elif isinstance(stmt, ast.Print):
            self._check_expr(stmt.value, local_vars)
        elif isinstance(stmt, ast.Return):
            if stmt.value:
                self._check_expr(stmt.value, local_vars)
        elif isinstance(stmt, ast.BufferCreate):
            local_vars[stmt.name] = types.BUFFER
        elif isinstance(stmt, ast.BorrowSlice):
            self._check_expr(stmt.buffer, local_vars, allow_move=False)
            owner_name = self._extract_name(stmt.buffer)
            if owner_name:
                self._register_borrow(owner_name, stmt.mutable, stmt.name, stmt)
            local_vars[stmt.name] = types.VIEW
        elif isinstance(stmt, ast.Move):
            if isinstance(stmt.src, ast.Name):
                self._move_if_needed(stmt.src.value, local_vars, stmt, stmt.src.span)
            local_vars[stmt.dst] = self._type_of_expr(stmt.src, local_vars)
        elif isinstance(stmt, ast.Release):
            self._check_expr(stmt.target, local_vars, allow_move=False)
            target_name = self._extract_name(stmt.target)
            if target_name:
                if self.active_borrows.get(target_name):
                    if not self._borrows_expired(target_name, stmt):
                        if not self._in_unsafe():
                            self.errors.append(
                                self._diag(
                                    stmt,
                                    f"Cannot release '{target_name}' while borrows are alive",
                                )
                            )
                        self.active_borrows[target_name] = []
                    else:
                        self.active_borrows[target_name] = []
        elif isinstance(stmt, ast.FunctionDef):
            self._check_function(stmt)
        elif isinstance(stmt, ast.ExternFunctionDef):
            return
        elif isinstance(stmt, ast.Import):
            return
        elif isinstance(stmt, ast.Break):
            return
        elif isinstance(stmt, ast.Continue):
            return

    def _check_expr(self, expr: ast.Expr, local_vars: Dict[str, types.Type], allow_move: bool = True) -> types.Type:
        if isinstance(expr, ast.Name):
            if self.moved.get(expr.value, False):
                moved_span = self.moved_at.get(expr.value)
                if moved_span:
                    msg = f"Use after move: {expr.value} (moved at L{moved_span.line_start}:{moved_span.column_start})"
                else:
                    msg = f"Use after move: {expr.value}"
                if not self._in_unsafe():
                    self.errors.append(self._diag(expr, msg))
            t = local_vars.get(expr.value, types.UNIT)
            return t
        if isinstance(expr, ast.BorrowExpr):
            owner_name = self._extract_name(expr.value)
            self._check_expr(expr.value, local_vars, allow_move=False)
            return self.type_info.expr_types.get(id(expr), types.VIEW)
        if isinstance(expr, ast.CopyExpr):
            self._check_expr(expr.value, local_vars, allow_move=False)
            return self.type_info.expr_types.get(id(expr), types.UNIT)
        if isinstance(expr, ast.MemberAccess):
            self._check_expr(expr.value, local_vars, allow_move=False)
            return self.type_info.expr_types.get(id(expr), types.UNIT)
        if isinstance(expr, ast.Call):
            for arg in expr.args:
                self._check_expr(arg, local_vars)
            return self.type_info.expr_types.get(id(expr), types.UNIT)
        if isinstance(expr, ast.IntLit):
            return types.INT
        if isinstance(expr, ast.StringLit):
            return types.STRING
        if isinstance(expr, ast.BoolLit):
            return types.BOOL
        if isinstance(expr, ast.BinOp):
            self._check_expr(expr.left, local_vars)
            self._check_expr(expr.right, local_vars)
            left_type = self._type_of_expr(expr.left, local_vars)
            right_type = self._type_of_expr(expr.right, local_vars)
            if not left_type.is_copy or not right_type.is_copy:
                if not self._in_unsafe():
                    self.errors.append(
                        self._diag(expr, "Arithmetic operands must be Copy types"),
                    )
            return self.type_info.expr_types.get(id(expr), types.UNIT)
        if isinstance(expr, ast.UnaryOp):
            self._check_expr(expr.value, local_vars)
            value_type = self._type_of_expr(expr.value, local_vars)
            if not value_type.is_copy:
                self.errors.append(
                    self._diag(expr, "Unary arithmetic requires Copy type"),
                )
            return self.type_info.expr_types.get(id(expr), types.UNIT)
        if isinstance(expr, ast.LogicalOp):
            self._check_expr(expr.left, local_vars)
            self._check_expr(expr.right, local_vars)
            return self.type_info.expr_types.get(id(expr), types.UNIT)
        if isinstance(expr, ast.TryExpr):
            return self._check_expr(expr.value, local_vars)
        return types.UNIT

    def _check_pattern_exprs(self, pattern: ast.Pattern, local_vars: Dict[str, types.Type]) -> None:
        if isinstance(pattern, ast.LiteralPattern):
            self._check_expr(pattern.value, local_vars)
            return
        if isinstance(pattern, ast.BindPattern):
            return
        if isinstance(pattern, ast.StructPattern):
            for field in pattern.fields:
                self._check_pattern_exprs(field, local_vars)
            return
        if isinstance(pattern, ast.EnumPattern):
            if pattern.payload:
                self._check_pattern_exprs(pattern.payload, local_vars)

    def _borrows_expired(self, owner: str, stmt: ast.Stmt) -> bool:
        node_id = self.stmt_node.get(id(stmt))
        if node_id is None:
            return False
        live = self.live_out.get(node_id, set())
        for info in self.active_borrows.get(owner, []):
            if info.var_name in live:
                return False
        return True

    def _prune_dead_borrows(self, stmt: ast.Stmt) -> None:
        node_id = self.stmt_node.get(id(stmt))
        if node_id is None:
            return
        live = self.live_in.get(node_id, set())
        for owner, borrows in list(self.active_borrows.items()):
            alive = [b for b in borrows if b.var_name in live]
            if alive:
                self.active_borrows[owner] = alive
            else:
                self.active_borrows[owner] = []

    def _analyze_cfg(self, stmts: List[ast.Stmt]) -> None:
        nodes, entry, exits = self._build_cfg(stmts)
        self.stmt_node = {id(node.stmt): node.node_id for node in nodes if node.stmt is not None}
        self.borrow_var_owner = self._collect_borrow_mapping(nodes)
        self.live_in, self.live_out = self._compute_liveness(nodes)

    @dataclass
    class _CFGNode:
        node_id: int
        stmt: Optional[ast.Stmt]
        uses: Set[str]
        defs: Set[str]
        succs: List[int]

    def _build_cfg(self, stmts: List[ast.Stmt]) -> Tuple[List["_CFGNode"], Optional[int], List[int]]:
        nodes: List[BorrowChecker._CFGNode] = []
        next_id = 0

        def new_node(stmt: Optional[ast.Stmt], uses: Set[str], defs: Set[str]) -> BorrowChecker._CFGNode:
            nonlocal next_id
            node = BorrowChecker._CFGNode(node_id=next_id, stmt=stmt, uses=uses, defs=defs, succs=[])
            nodes.append(node)
            next_id += 1
            return node

        def build_block(block: List[ast.Stmt], known_vars: Set[str], nested: bool) -> Tuple[Optional[int], List[int], Set[str]]:
            entry_id: Optional[int] = None
            exits: List[int] = []
            new_vars: Set[str] = set()
            for stmt in block:
                sub_entry, sub_exits, sub_new = build_stmt(stmt, known_vars)
                if entry_id is None:
                    entry_id = sub_entry
                for exit_id in exits:
                    if sub_entry is not None:
                        nodes[exit_id].succs.append(sub_entry)
                exits = sub_exits
                new_vars |= sub_new
            if nested and new_vars:
                kill = new_node(None, set(), new_vars)
                for exit_id in exits:
                    nodes[exit_id].succs.append(kill.node_id)
                exits = [kill.node_id]
            return entry_id, exits, new_vars

        def register_defs(defs: Set[str], known_vars: Set[str], new_vars: Set[str]) -> None:
            for name in defs:
                if name not in known_vars:
                    new_vars.add(name)
                    known_vars.add(name)

        def build_stmt(stmt: ast.Stmt, known_vars: Set[str]) -> Tuple[Optional[int], List[int], Set[str]]:
            if isinstance(stmt, ast.Return):
                node = new_node(stmt, self._uses_in_stmt(stmt), set())
                return node.node_id, [], set()
            if isinstance(stmt, ast.UnsafeBlock):
                return build_block(stmt.body, known_vars, nested=True)
            if isinstance(stmt, ast.If):
                header = new_node(stmt, self._uses_in_expr(stmt.condition), set())
                branch_vars = set(known_vars)
                body_entry, body_exits, body_new = build_block(stmt.body, branch_vars, nested=True)
                join = new_node(None, set(), body_new)
                header.succs.append(join.node_id)
                if body_entry is not None:
                    header.succs.append(body_entry)
                    for exit_id in body_exits:
                        nodes[exit_id].succs.append(join.node_id)
                return header.node_id, [join.node_id], set()
            if isinstance(stmt, ast.Repeat):
                header = new_node(stmt, self._uses_in_expr(stmt.count), set())
                loop_vars = set(known_vars)
                body_entry, body_exits, body_new = build_block(stmt.body, loop_vars, nested=False)
                kill = new_node(None, set(), body_new)
                header.succs.append(kill.node_id)
                if body_entry is not None:
                    header.succs.append(body_entry)
                    for exit_id in body_exits:
                        nodes[exit_id].succs.append(header.node_id)
                return header.node_id, [kill.node_id], set()
            if isinstance(stmt, ast.While):
                header = new_node(stmt, self._uses_in_expr(stmt.condition), set())
                loop_vars = set(known_vars)
                body_entry, body_exits, body_new = build_block(stmt.body, loop_vars, nested=False)
                kill = new_node(None, set(), body_new)
                header.succs.append(kill.node_id)
                if body_entry is not None:
                    header.succs.append(body_entry)
                    for exit_id in body_exits:
                        nodes[exit_id].succs.append(header.node_id)
                return header.node_id, [kill.node_id], set()
            defs = self._defs_in_stmt(stmt)
            node = new_node(stmt, self._uses_in_stmt(stmt), defs)
            new_vars: Set[str] = set()
            register_defs(defs, known_vars, new_vars)
            return node.node_id, [node.node_id], new_vars

        entry, exits, _ = build_block(stmts, set(), nested=False)
        return nodes, entry, exits

    def _compute_liveness(self, nodes: List["_CFGNode"]) -> Tuple[Dict[int, Set[str]], Dict[int, Set[str]]]:
        live_in: Dict[int, Set[str]] = {n.node_id: set() for n in nodes}
        live_out: Dict[int, Set[str]] = {n.node_id: set() for n in nodes}
        changed = True
        while changed:
            changed = False
            for node in reversed(nodes):
                out_set: Set[str] = set()
                for succ in node.succs:
                    out_set |= live_in[succ]
                in_set = node.uses | (out_set - node.defs)
                if out_set != live_out[node.node_id] or in_set != live_in[node.node_id]:
                    live_out[node.node_id] = out_set
                    live_in[node.node_id] = in_set
                    changed = True
        return live_in, live_out

    def _collect_borrow_mapping(self, nodes: List["_CFGNode"]) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for node in nodes:
            stmt = node.stmt
            if isinstance(stmt, ast.BorrowSlice):
                owner = self._extract_name(stmt.buffer)
                if owner:
                    mapping[stmt.name] = owner
            if isinstance(stmt, ast.Assign):
                if isinstance(stmt.target, ast.Name) and isinstance(stmt.value, ast.BorrowExpr):
                    owner = self._extract_name(stmt.value.value)
                    if owner:
                        mapping[stmt.target.value] = owner
        return mapping

    def _uses_in_stmt(self, stmt: ast.Stmt) -> Set[str]:
        uses: Set[str] = set()
        if isinstance(stmt, ast.Assign):
            uses |= self._uses_in_expr(stmt.value)
        elif isinstance(stmt, ast.AddAssign):
            uses |= self._uses_in_expr(stmt.target)
            uses |= self._uses_in_expr(stmt.value)
        elif isinstance(stmt, ast.Print):
            uses |= self._uses_in_expr(stmt.value)
        elif isinstance(stmt, ast.Return) and stmt.value:
            uses |= self._uses_in_expr(stmt.value)
        elif isinstance(stmt, ast.While):
            uses |= self._uses_in_expr(stmt.condition)
        elif isinstance(stmt, ast.BufferCreate):
            uses |= self._uses_in_expr(stmt.size)
        elif isinstance(stmt, ast.BorrowSlice):
            uses |= self._uses_in_expr(stmt.buffer)
            uses |= self._uses_in_expr(stmt.start)
            uses |= self._uses_in_expr(stmt.end)
        elif isinstance(stmt, ast.Move):
            uses |= self._uses_in_expr(stmt.src)
        elif isinstance(stmt, ast.Release):
            uses |= self._uses_in_expr(stmt.target)
        elif isinstance(stmt, ast.UnsafeBlock):
            for inner in stmt.body:
                uses |= self._uses_in_stmt(inner)
        return uses

    def _defs_in_stmt(self, stmt: ast.Stmt) -> Set[str]:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.target, ast.Name):
            return {stmt.target.value}
        if isinstance(stmt, ast.AddAssign) and isinstance(stmt.target, ast.Name):
            return {stmt.target.value}
        if isinstance(stmt, ast.BufferCreate):
            return {stmt.name}
        if isinstance(stmt, ast.BorrowSlice):
            return {stmt.name}
        if isinstance(stmt, ast.Move):
            return {stmt.dst}
        return set()

    def _uses_in_expr(self, expr: ast.Expr) -> Set[str]:
        uses: Set[str] = set()
        if isinstance(expr, ast.Name):
            uses.add(expr.value)
        elif isinstance(expr, ast.Call):
            for arg in expr.args:
                uses |= self._uses_in_expr(arg)
        elif isinstance(expr, ast.BorrowExpr):
            uses |= self._uses_in_expr(expr.value)
        elif isinstance(expr, ast.CopyExpr):
            uses |= self._uses_in_expr(expr.value)
        elif isinstance(expr, ast.MemberAccess):
            uses |= self._uses_in_expr(expr.value)
        elif isinstance(expr, ast.BinOp):
            uses |= self._uses_in_expr(expr.left)
            uses |= self._uses_in_expr(expr.right)
        elif isinstance(expr, ast.UnaryOp):
            uses |= self._uses_in_expr(expr.value)
        return uses

    def _register_borrow(self, owner: str, mutable: bool, var_name: str, stmt: ast.Stmt) -> None:
        node_id = self.stmt_node.get(id(stmt))
        live = self.live_in.get(node_id, set()) if node_id is not None else set()
        for borrow_var, borrow_owner in self.borrow_var_owner.items():
            if borrow_owner != owner:
                continue
            if borrow_var not in live:
                continue
            existing_mut = self.borrow_var_mutable.get(borrow_var, False)
            if mutable or existing_mut:
                conflict = "mutable" if mutable else "immutable"
                existing = "mutable" if existing_mut else "immutable"
                if not self._in_unsafe():
                    self.errors.append(
                        self._diag(
                            stmt,
                            f"Borrow conflict: {conflict} borrow overlaps {existing} borrow '{borrow_var}'",
                        )
                    )
                    return
        info = BorrowInfo(owner=owner, mutable=mutable, var_name=var_name)
        existing = self.active_borrows.get(owner, [])
        existing.append(info)
        self.active_borrows[owner] = existing
        self.borrow_var_owner[var_name] = owner
        self.borrow_var_mutable[var_name] = mutable
        if self.scope_stack:
            self.scope_stack[-1].append(info)

    def _move_if_needed(
        self,
        name: str,
        local_vars: Dict[str, types.Type],
        stmt: Optional[ast.Stmt],
        span: Optional[diagnostics.Span],
    ) -> None:
        t = local_vars.get(name)
        if t is None:
            return
        if not t.is_copy:
            if stmt is not None and self.active_borrows.get(name):
                if not self._borrows_expired(name, stmt) and not self._in_unsafe():
                    self.errors.append(self._diag(stmt, f"Cannot move '{name}' while it is borrowed"))
                    return
            self.moved[name] = True
            if span:
                self.moved_at[name] = span

    def _extract_name(self, expr: ast.Expr) -> Optional[str]:
        if isinstance(expr, ast.Name):
            return expr.value
        return None

    def _type_of_expr(self, expr: ast.Expr, local_vars: Dict[str, types.Type]) -> types.Type:
        if isinstance(expr, ast.Name):
            return local_vars.get(expr.value, types.UNIT)
        return self.type_info.expr_types.get(id(expr), types.UNIT)

    def _type_of_name(self, name: str, local_vars: Dict[str, types.Type]) -> types.Type:
        return local_vars.get(name, types.UNIT)

    def _enter_scope(self) -> None:
        self.scope_stack.append([])

    def _exit_scope(self) -> None:
        if not self.scope_stack:
            return
        borrows = self.scope_stack.pop()
        for info in borrows:
            owner_borrows = self.active_borrows.get(info.owner, [])
            self.active_borrows[info.owner] = [b for b in owner_borrows if b is not info]

    def _in_unsafe(self) -> bool:
        return bool(self.unsafe_stack and self.unsafe_stack[-1])

    def _resolve_type(self, tref: ast.TypeRef) -> types.Type:
        name = tref.name
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
        if name in ("unit", "void", "없음"):
            return types.UNIT
        return types.Type(name=name, is_copy=False)

    def _diag(self, node: object, message: str) -> diagnostics.Diagnostic:
        span = getattr(node, "span", None) if node is not None else None
        if self.current_function:
            message = f"{message} (in fn {self.current_function})"
        return diagnostics.Diagnostic(message=message, span=span)


