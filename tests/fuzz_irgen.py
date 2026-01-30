from __future__ import annotations

import random
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "compiler-bootstrap"))
sys.path.insert(0, str(ROOT / "compiler-core"))

from compiler_bootstrap import borrowcheck, irgen, parser, typecheck  # noqa: E402


def main() -> int:
    for _ in range(200):
        source = _random_source()
        try:
            module = parser.parse(source)
        except Exception:
            continue
        checker = typecheck.TypeChecker()
        info = checker.check_module(module)
        if checker.errors:
            continue
        borrow = borrowcheck.BorrowChecker(info)
        borrow.check_module(module)
        if borrow.errors:
            continue
        try:
            irgen.IRGen(expr_types=info.expr_types).lower_module(module)
        except Exception:
            return 1
    print("fuzz_irgen: ok")
    return 0


def _random_source() -> str:
    alphabet = string.ascii_letters + string.digits + " 모듈함수를정의한다:+=<>\"_"
    lines = ["module fuzz_irgen"]
    for _ in range(8):
        line = "".join(random.choice(alphabet) for _ in range(20))
        lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

