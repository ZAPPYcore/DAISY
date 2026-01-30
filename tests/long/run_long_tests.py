from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "compiler-bootstrap"))
sys.path.insert(0, str(ROOT / "compiler-core"))

from compiler_bootstrap.driver import compile_file  # noqa: E402


def main() -> int:
    loops = 5
    for idx in range(loops):
        print(f"long test pass {idx + 1}/{loops}")
        code = subprocess.call([sys.executable, str(ROOT / "tests" / "run_tests.py")])
        if code != 0:
            return code
    sanitize = os.environ.get("DAISY_SANITIZE")
    if not _run_and_check(
        ROOT / "tests" / "long" / "stress_runtime.dsy",
        ROOT / "tests" / "expected" / "stress_runtime.txt",
        sanitize,
    ):
        return 1
    if not _run_and_check(
        ROOT / "tests" / "long" / "strings_stress.dsy",
        ROOT / "tests" / "expected" / "strings_stress.txt",
        sanitize,
    ):
        return 1
    if not _run_and_check(
        ROOT / "tests" / "long" / "collections_stress.dsy",
        ROOT / "tests" / "expected" / "collections_stress.txt",
        sanitize,
    ):
        return 1
    if not _run_and_check(
        ROOT / "tests" / "long" / "concurrency_stress.dsy",
        ROOT / "tests" / "expected" / "concurrency_stress.txt",
        sanitize,
    ):
        return 1
    if not _run_and_check(
        ROOT / "tests" / "long" / "fs_stress.dsy",
        ROOT / "tests" / "expected" / "fs_stress.txt",
        sanitize,
    ):
        return 1
    if not _run_and_check(
        ROOT / "tests" / "long" / "io_dos.dsy",
        ROOT / "tests" / "expected" / "io_dos.txt",
        sanitize,
    ):
        return 1
    if not _run_with_net_server(
        ROOT / "tests" / "long" / "net_stress.dsy",
        ROOT / "tests" / "expected" / "net_stress.txt",
        sanitize,
        loops=3,
    ):
        return 1
    if not _run_with_net_server(
        ROOT / "tests" / "long" / "net_dos.dsy",
        ROOT / "tests" / "expected" / "net_dos.txt",
        sanitize,
        loops=50,
    ):
        return 1
    rt_checks = subprocess.call(
        [sys.executable, str(ROOT / "tools" / "cli" / "daisy.py"), "build", "--rt-checks", "examples/english_hello.dsy"]
    )
    if rt_checks != 0:
        return rt_checks
    if sanitize:
        sanitize_code = subprocess.call(
            [
                sys.executable,
                str(ROOT / "tools" / "cli" / "daisy.py"),
                "build",
                "--sanitize",
                sanitize,
                "examples/english_hello.dsy",
            ]
        )
        if sanitize_code != 0:
            return sanitize_code
    bench = subprocess.call([sys.executable, str(ROOT / "bench" / "bench.py")])
    return bench


def _run_and_check(path: Path, expected_output: Path, sanitize: str | None) -> bool:
    try:
        result = compile_file(path, ROOT / "build", rt_checks=True, sanitize=sanitize)
    except RuntimeError as exc:
        print(f"unexpected failure: {path}\n{exc}")
        return False
    completed = subprocess.run([str(result.exe_path)], capture_output=True, text=True)
    if completed.returncode != 0:
        print(f"execution failed: {path}\nexit: {completed.returncode}")
        return False
    expected = expected_output.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    actual = completed.stdout.replace("\r\n", "\n").strip()
    if actual != expected:
        print(f"output mismatch: {path}\nexpected:\n{expected}\nactual:\n{actual}")
        return False
    return True


def _run_with_net_server(path: Path, expected_output: Path, sanitize: str | None, loops: int = 3) -> bool:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def handler() -> None:
        try:
            conn, _addr = server.accept()
            for _ in range(loops):
                _ = conn.recv(1024)
                conn.sendall(b"pong")
            conn.close()
        finally:
            server.close()

    thread = threading.Thread(target=handler, daemon=True)
    thread.start()
    source = path.read_text(encoding="utf-8")
    generated = ROOT / "build" / f"_net_stress_{port}.dsy"
    generated.write_text(source.replace("PORT_PLACEHOLDER", str(port)), encoding="utf-8")
    ok = _run_and_check(generated, expected_output, sanitize)
    thread.join(timeout=2.0)
    return ok


if __name__ == "__main__":
    raise SystemExit(main())

