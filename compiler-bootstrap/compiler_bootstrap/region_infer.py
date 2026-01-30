from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from compiler_core import ast


@dataclass
class RegionInfo:
    regions: Dict[str, str]
    errors: List[str]


class RegionInfer:
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.region_of: Dict[str, str] = {}
        self.counter = 0

    def infer(self, func: ast.FunctionDef) -> RegionInfo:
        self.errors = []
        self.region_of = {}
        self.counter = 0
        for stmt in func.body:
            self._visit_stmt(stmt, current_region=None)
        return RegionInfo(regions=self.region_of, errors=self.errors)

    def _new_region(self) -> str:
        self.counter += 1
        return f"r{self.counter}"

    def _visit_stmt(self, stmt: ast.Stmt, current_region: Optional[str]) -> None:
        if isinstance(stmt, ast.BufferCreate):
            region = self._new_region()
            self.region_of[stmt.name] = region
        elif isinstance(stmt, ast.BorrowSlice):
            owner = self._extract_name(stmt.buffer)
            if owner and owner in self.region_of:
                self.region_of[stmt.name] = self.region_of[owner]
        elif isinstance(stmt, ast.Assign):
            if isinstance(stmt.target, ast.Name) and isinstance(stmt.value, ast.Name):
                if stmt.value.value in self.region_of:
                    self.region_of[stmt.target.value] = self.region_of[stmt.value.value]
        elif isinstance(stmt, ast.If):
            regions_before = dict(self.region_of)
            self._visit_block(stmt.body)
            regions_after = dict(self.region_of)
            self.region_of = self._merge_regions(regions_before, regions_after)
        elif isinstance(stmt, ast.Repeat):
            regions_before = dict(self.region_of)
            self._visit_block(stmt.body)
            regions_after = dict(self.region_of)
            self.region_of = self._merge_regions(regions_before, regions_after)
        elif isinstance(stmt, ast.While):
            regions_before = dict(self.region_of)
            self._visit_block(stmt.body)
            regions_after = dict(self.region_of)
            self.region_of = self._merge_regions(regions_before, regions_after)

    def _visit_block(self, stmts: List[ast.Stmt]) -> None:
        for stmt in stmts:
            self._visit_stmt(stmt, current_region=None)

    def _merge_regions(self, a: Dict[str, str], b: Dict[str, str]) -> Dict[str, str]:
        merged = dict(a)
        for name, region in b.items():
            if name in merged and merged[name] != region:
                self.errors.append(f"Region mismatch for {name}: {merged[name]} vs {region}")
                merged[name] = merged[name]
            else:
                merged[name] = region
        return merged

    def _extract_name(self, expr: ast.Expr) -> Optional[str]:
        if isinstance(expr, ast.Name):
            return expr.value
        return None

