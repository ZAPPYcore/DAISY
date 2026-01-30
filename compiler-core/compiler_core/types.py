from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Type:
    name: str
    is_copy: bool = False

    def __str__(self) -> str:
        return self.name


INT = Type("int", is_copy=True)
BOOL = Type("bool", is_copy=True)
STRING = Type("string", is_copy=False)
BUFFER = Type("buffer", is_copy=False)
VIEW = Type("view", is_copy=False)
TENSOR = Type("tensor", is_copy=False)
CHANNEL = Type("channel", is_copy=False)
VEC = Type("vec", is_copy=False)
UNIT = Type("unit", is_copy=True)


@dataclass(frozen=True)
class RefType:
    target: Type
    mutable: bool
    region: Optional[str] = None

    def __str__(self) -> str:
        prefix = "&mut " if self.mutable else "&"
        return f"{prefix}{self.target}"


