from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class IRExtern:
    name: str
    params: List["IRParam"]
    return_type: str


@dataclass
class IRStructField:
    name: str
    type_name: str


@dataclass
class IRStruct:
    name: str
    fields: List[IRStructField]


@dataclass
class IREnumCase:
    name: str
    payload: Optional[str] = None


@dataclass
class IREnum:
    name: str
    cases: List[IREnumCase]


@dataclass
class IRModule:
    name: str
    functions: List["IRFunction"]
    externs: List["IRExtern"]
    structs: List[IRStruct] = field(default_factory=list)
    enums: List[IREnum] = field(default_factory=list)


@dataclass
class IRFunction:
    name: str
    params: List["IRParam"]
    return_type: str
    blocks: List["BasicBlock"]


@dataclass
class IRParam:
    name: str
    type_name: str


@dataclass
class BasicBlock:
    label: str
    instructions: List["Instr"]


@dataclass
class Instr:
    op: str
    args: List[str] = field(default_factory=list)
    result: Optional[str] = None
    type_name: Optional[str] = None


