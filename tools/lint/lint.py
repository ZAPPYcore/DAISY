from __future__ import annotations

from pathlib import Path
from typing import List


def run_lint(path: Path) -> int:
    files = list(path.rglob("*.dsy")) if path.is_dir() else [path]
    errors: List[str] = []
    for file in files:
        lines = file.read_text(encoding="utf-8").splitlines()
        if not lines:
            continue
        if not lines[0].startswith("module") and not lines[0].startswith("모듈"):
            errors.append(f"{file}: first line must declare module")
        for idx, line in enumerate(lines, start=1):
            if "\t" in line:
                errors.append(f"{file}:{idx} contains tab character")
            if line.rstrip() != line:
                errors.append(f"{file}:{idx} has trailing whitespace")
    if errors:
        print("\n".join(errors))
        return 1
    print("lint: ok")
    return 0


