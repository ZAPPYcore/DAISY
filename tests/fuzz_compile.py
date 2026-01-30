from __future__ import annotations

import random
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "compiler-bootstrap"))
sys.path.insert(0, str(ROOT / "compiler-core"))

from compiler_bootstrap import borrowcheck, parser, typecheck  # noqa: E402


def main() -> int:
    for _ in range(200):
        source = _random_source()
        try:
            module = parser.parse(source)
        except Exception:
            continue
        try:
            checker = typecheck.TypeChecker()
            info = checker.check_module(module)
            borrow = borrowcheck.BorrowChecker(info)
            borrow.check_module(module)
        except Exception:
            # Fuzzing should never crash the compiler pipeline.
            return 1
    print("fuzz_compile: ok")
    return 0


def _random_source() -> str:
    alphabet = string.ascii_letters + string.digits + " 모듈함수를정의한다:+=<>\"_"
    lines = ["module fuzz_compile"]
    for _ in range(8):
        line = "".join(random.choice(alphabet) for _ in range(20))
        lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

