from __future__ import annotations

from pathlib import Path
from typing import List


def run_docgen(path: Path) -> int:
    files = list(path.rglob("*.dsy")) if path.is_dir() else [path]
    docs: List[str] = ["# DAISY API Docs", ""]
    for file in files:
        lines = file.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if line.startswith("fn "):
                docs.append(f"- {line}")
            if line.startswith("함수를 정의한다") or line.startswith("함수 "):
                docs.append(f"- {line}")
    out = Path("docs") / "api.md"
    out.write_text("\n".join(docs) + "\n", encoding="utf-8")
    print(f"docgen: wrote {out}")
    return 0


