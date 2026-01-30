from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Union

from compiler_core.diagnostics import Span


@dataclass
class Module:
    name: str
    body: List["Stmt"]
    span: Optional[Span] = None


@dataclass
class TypeParam:
    name: str
    bounds: List[str]
    span: Optional[Span] = None


@dataclass
class FunctionDef:
    name: str
    type_params: List[TypeParam]
    params: List["Param"]
    return_type: "TypeRef"
    body: List["Stmt"]
    is_public: bool = False
    span: Optional[Span] = None


@dataclass
class ExternFunctionDef:
    name: str
    params: List["Param"]
    return_type: "TypeRef"
    is_public: bool = False
    span: Optional[Span] = None


@dataclass
class StructField:
    name: str
    type_ref: "TypeRef"
    span: Optional[Span] = None


@dataclass
class StructDef:
    name: str
    type_params: List[TypeParam]
    fields: List[StructField]
    is_public: bool = False
    span: Optional[Span] = None


@dataclass
class EnumCase:
    name: str
    payload: Optional["TypeRef"] = None
    span: Optional[Span] = None


@dataclass
class EnumDef:
    name: str
    type_params: List[TypeParam]
    cases: List[EnumCase]
    is_public: bool = False
    span: Optional[Span] = None


@dataclass
class Import:
    module: str
    alias: Optional[str] = None
    is_use: bool = False
    span: Optional[Span] = None


@dataclass
class Param:
    name: str
    type_ref: "TypeRef"
    span: Optional[Span] = None


@dataclass
class TypeRef:
    name: str
    args: List["TypeRef"] = None
    span: Optional[Span] = None


@dataclass
class Assign:
    target: "Expr"
    value: "Expr"
    span: Optional[Span] = None


@dataclass
class AddAssign:
    target: "Expr"
    value: "Expr"
    span: Optional[Span] = None


@dataclass
class If:
    condition: "Expr"
    body: List["Stmt"]
    else_body: Optional[List["Stmt"]] = None
    span: Optional[Span] = None


@dataclass
class Repeat:
    count: "Expr"
    body: List["Stmt"]
    span: Optional[Span] = None


@dataclass
class While:
    condition: "Expr"
    body: List["Stmt"]
    span: Optional[Span] = None


@dataclass
class MatchCase:
    pattern: "Pattern"
    body: List["Stmt"]
    guard: Optional["Expr"] = None
    span: Optional[Span] = None


@dataclass
class Pattern:
    pass


@dataclass
class WildcardPattern(Pattern):
    span: Optional[Span] = None


@dataclass
class LiteralPattern(Pattern):
    value: "Expr"
    span: Optional[Span] = None


@dataclass
class BindPattern(Pattern):
    name: str
    span: Optional[Span] = None


@dataclass
class StructPattern(Pattern):
    struct_name: str
    fields: List["Pattern"]
    span: Optional[Span] = None


@dataclass
class EnumPattern(Pattern):
    enum_name: str
    case_name: str
    payload: Optional["Pattern"] = None
    binding: Optional[str] = None
    span: Optional[Span] = None


@dataclass
class TraitMethod:
    name: str
    params: List["Param"]
    return_type: "TypeRef"
    span: Optional[Span] = None


@dataclass
class TraitDef:
    name: str
    type_params: List[TypeParam]
    methods: List[TraitMethod]
    is_public: bool = False
    span: Optional[Span] = None


@dataclass
class ImplDef:
    trait_name: Optional[str]
    for_type: "TypeRef"
    methods: List[FunctionDef]
    span: Optional[Span] = None


@dataclass
class Match:
    value: "Expr"
    cases: List[MatchCase]
    else_body: Optional[List["Stmt"]] = None
    span: Optional[Span] = None


@dataclass
class Print:
    value: "Expr"
    span: Optional[Span] = None


@dataclass
class Return:
    value: Optional["Expr"]
    span: Optional[Span] = None


@dataclass
class Break:
    span: Optional[Span] = None


@dataclass
class Continue:
    span: Optional[Span] = None


@dataclass
class UnsafeBlock:
    reason: Optional[str]
    body: List["Stmt"]
    span: Optional[Span] = None


@dataclass
class BufferCreate:
    name: str
    size: "Expr"
    span: Optional[Span] = None


@dataclass
class BorrowSlice:
    name: str
    buffer: "Expr"
    start: "Expr"
    end: "Expr"
    mutable: bool
    span: Optional[Span] = None


@dataclass
class Move:
    src: "Expr"
    dst: str
    span: Optional[Span] = None


@dataclass
class Release:
    target: "Expr"
    span: Optional[Span] = None


@dataclass
class BorrowExpr:
    value: "Expr"
    mutable: bool
    span: Optional[Span] = None


@dataclass
class CopyExpr:
    value: "Expr"
    span: Optional[Span] = None


@dataclass
class Call:
    callee: str
    args: List["Expr"]
    span: Optional[Span] = None


@dataclass
class MemberAccess:
    value: "Expr"
    name: str
    span: Optional[Span] = None


@dataclass
class BinOp:
    left: "Expr"
    op: str
    right: "Expr"
    span: Optional[Span] = None


@dataclass
class UnaryOp:
    op: str
    value: "Expr"
    span: Optional[Span] = None


@dataclass
class LogicalOp:
    left: "Expr"
    op: str
    right: "Expr"
    span: Optional[Span] = None


@dataclass
class TryExpr:
    value: "Expr"
    span: Optional[Span] = None


@dataclass
class Name:
    value: str
    span: Optional[Span] = None


@dataclass
class IntLit:
    value: int
    span: Optional[Span] = None


@dataclass
class StringLit:
    value: str
    span: Optional[Span] = None


@dataclass
class BoolLit:
    value: bool
    span: Optional[Span] = None


Expr = Union[Name, IntLit, StringLit, BoolLit, BorrowExpr, CopyExpr, Call, MemberAccess, BinOp, UnaryOp, LogicalOp, TryExpr]
Pattern = Union[WildcardPattern, LiteralPattern, BindPattern, StructPattern, EnumPattern]
Stmt = Union[
    Assign,
    AddAssign,
    If,
    Repeat,
    While,
    Match,
    Print,
    Return,
    Break,
    Continue,
    UnsafeBlock,
    BufferCreate,
    BorrowSlice,
    Move,
    Release,
    FunctionDef,
    ExternFunctionDef,
    StructDef,
    EnumDef,
    TraitDef,
    ImplDef,
    Import,
]


