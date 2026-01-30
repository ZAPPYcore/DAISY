from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env = dict(os.environ)
    env.setdefault("DAISY_SANITIZE", "address")
    commands = [
        [sys.executable, "tools/cli/daisy.py", "build", "examples/english_hello.dsy"],
        [sys.executable, "tools/cli/daisy.py", "build", "examples/korean_hello.dsy"],
        [sys.executable, "tools/cli/daisy.py", "build", "examples/tensor_matmul.dsy"],
        [sys.executable, "tools/cli/daisy.py", "build", "examples/concurrency.dsy"],
        [sys.executable, "tools/cli/daisy.py", "test"],
        [sys.executable, "tools/security/audit.py"],
        [sys.executable, "tools/security/supply_chain_audit.py"],
        [sys.executable, "tests/security/run_security_tests.py"],
        [sys.executable, "tests/fuzz_lexer.py"],
        [sys.executable, "tests/fuzz_compile.py"],
        [sys.executable, "tests/fuzz_irgen.py"],
        [sys.executable, "tools/cli/daisy.py", "test", "--long"],
        [sys.executable, "tools/cli/daisy.py", "build-stage1"],
    ]
    for cmd in commands:
        code = subprocess.call(cmd, cwd=str(ROOT), env=env)
        if code != 0:
            return code
    cargo = shutil.which("cargo")
    if cargo:
        rust_cmds = [
            [cargo, "build", "--manifest-path", "examples/rust_crate/Cargo.toml"],
            [cargo, "build", "--manifest-path", "examples/rust_calls_daisy/Cargo.toml"],
        ]
        for cmd in rust_cmds:
            code = subprocess.call(cmd, cwd=str(ROOT))
            if code != 0:
                return code
    else:
        print("cargo not found; skipping rust interop builds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

