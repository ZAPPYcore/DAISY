from __future__ import annotations

import random
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "compiler-bootstrap"))
sys.path.insert(0, str(ROOT / "compiler-core"))

from compiler_bootstrap import parser  # noqa: E402


def main() -> int:
    for _ in range(100):
        data = _random_source()
        try:
            parser.parse(data)
        except Exception:
            pass
    print("fuzz: ok")
    return 0


def _random_source() -> str:
    alphabet = string.ascii_letters + string.digits + " 모듈함수를정의한다:+=<>\""
    lines = ["module fuzz"]
    for _ in range(5):
        line = "".join(random.choice(alphabet) for _ in range(10))
        lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())


