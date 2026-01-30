from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "compiler-bootstrap"))
sys.path.insert(0, str(ROOT / "compiler-core"))

from compiler_bootstrap.driver import compile_file  # noqa: E402


def main() -> int:
    failures = 0
    if not _expect_script_success(ROOT / "tests" / "fuzz_lexer.py"):
        failures += 1
    if not _expect_script_success(ROOT / "tests" / "fuzz_compile.py"):
        failures += 1
    if not _expect_script_success(ROOT / "tests" / "fuzz_irgen.py"):
        failures += 1
    if not _expect_compile_failure(ROOT / "tests" / "borrow_fail.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "examples" / "english_hello.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "arithmetic.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "comparison.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "module_import.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "module_use_alias.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "korean_module_alias.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "deps_import.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "workspace_import.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "unsafe_reason_ok.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "unsafe_release_ok.dsy"):
        failures += 1
    if not _expect_compile_failure(ROOT / "tests" / "unsafe_reason_fail.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "unsafe_borrow_conflict_fail.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "error_model.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "match_basic.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "match_enum_bind.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "match_guard.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "match_nested_enum.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "match_struct.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "try_result_basic.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "try_option_basic.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "try_korean_basic.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "result_option_utils.dsy"):
        failures += 1
    if not _expect_run_success(
        ROOT / "tests" / "result_option_utils.dsy",
        ROOT / "tests" / "expected" / "result_option_utils.txt",
    ):
        failures += 1
    if not _expect_run_success(
        ROOT / "tests" / "strings_runtime.dsy",
        ROOT / "tests" / "expected" / "strings_runtime.txt",
    ):
        failures += 1
    if not _expect_run_success(
        ROOT / "tests" / "strings_ext_runtime.dsy",
        ROOT / "tests" / "expected" / "strings_ext_runtime.txt",
    ):
        failures += 1
    if not _expect_run_success(
        ROOT / "tests" / "collections_runtime.dsy",
        ROOT / "tests" / "expected" / "collections_runtime.txt",
    ):
        failures += 1
    if not _expect_run_success(
        ROOT / "tests" / "runtime_stats.dsy",
        ROOT / "tests" / "expected" / "runtime_stats.txt",
    ):
        failures += 1
    if not _expect_run_success(
        ROOT / "tests" / "concurrency_runtime.dsy",
        ROOT / "tests" / "expected" / "concurrency_runtime.txt",
    ):
        failures += 1
    if not _expect_run_success(
        ROOT / "tests" / "fs_runtime.dsy",
        ROOT / "tests" / "expected" / "fs_runtime.txt",
    ):
        failures += 1
    if not _expect_run_with_net_server(
        ROOT / "tests" / "net_runtime.dsy",
        ROOT / "tests" / "expected" / "net_runtime.txt",
    ):
        failures += 1
    if not _expect_run_success(
        ROOT / "tests" / "stdlib_core_runtime.dsy",
        ROOT / "tests" / "expected" / "stdlib_core_runtime.txt",
    ):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "struct_basic.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "enum_basic.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "generic_fn_basic.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "generics_basic.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "trait_basic.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "trait_bounds_ok.dsy"):
        failures += 1
    if not _expect_compile_failure(ROOT / "tests" / "trait_bounds_fail.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "if_else.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "logical_ops.dsy"):
        failures += 1
    if not _expect_compile_success(ROOT / "tests" / "korean_struct_enum.dsy"):
        failures += 1
    if not _expect_compile_failure(ROOT / "tests" / "korean_private.dsy"):
        failures += 1
    if not _expect_compile_failure(ROOT / "tests" / "module_private.dsy"):
        failures += 1
    if failures:
        print(f"tests failed: {failures}")
        return 1
    print("tests: ok")
    return 0


def _expect_compile_failure(path: Path) -> bool:
    try:
        compile_file(path, ROOT / "build")
    except RuntimeError:
        return True
    print(f"expected failure but compiled: {path}")
    return False


def _expect_compile_success(path: Path) -> bool:
    try:
        compile_file(path, ROOT / "build")
        return True
    except RuntimeError as exc:
        print(f"unexpected failure: {path}\n{exc}")
        return False


def _expect_run_success(path: Path, expected_output: Path) -> bool:
    try:
        build_dir = _next_build_dir(path.stem)
        sanitize = os.environ.get("DAISY_SANITIZE")
        result = compile_file(path, build_dir, rt_checks=True, sanitize=sanitize)
    except RuntimeError as exc:
        print(f"unexpected failure: {path}\n{exc}")
        return False
    try:
        completed = __import__("subprocess").run(
            [str(result.exe_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        print(f"execution failed: {path}\n{exc}")
        return False
    if completed.returncode != 0:
        print(f"execution failed: {path}\nexit: {completed.returncode}")
        return False
    expected = expected_output.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    actual = completed.stdout.replace("\r\n", "\n").strip()
    if actual != expected:
        print(f"output mismatch: {path}\nexpected:\n{expected}\nactual:\n{actual}")
        return False
    return True


def _next_build_dir(stem: str) -> Path:
    unique = uuid.uuid4().hex[:8]
    return ROOT / "build" / "tests" / f"{stem}_{unique}"


def _expect_script_success(path: Path) -> bool:
    completed = subprocess.run([sys.executable, str(path)], capture_output=True, text=True)
    if completed.returncode != 0:
        print(f"script failed: {path}\n{completed.stderr}")
        return False
    return True


def _expect_run_with_net_server(path: Path, expected_output: Path) -> bool:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def handler() -> None:
        try:
            conn, _addr = server.accept()
            _ = conn.recv(1024)
            conn.sendall(b"pong")
            conn.close()
        finally:
            server.close()

    thread = threading.Thread(target=handler, daemon=True)
    thread.start()
    source = path.read_text(encoding="utf-8")
    generated = ROOT / "build" / f"_net_runtime_{port}.dsy"
    generated.write_text(source.replace("PORT_PLACEHOLDER", str(port)), encoding="utf-8")
    ok = _expect_run_success(generated, expected_output)
    thread.join(timeout=2.0)
    return ok


if __name__ == "__main__":
    raise SystemExit(main())


