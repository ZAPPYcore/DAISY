from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "compiler-bootstrap"))
sys.path.insert(0, str(ROOT / "compiler-core"))

from compiler_bootstrap.driver import compile_file  # noqa: E402


def main() -> int:
    failures = 0
    if not _expect_net_recv_oversize_failure(ROOT / "tests" / "security" / "net_recv_oversize.dsy"):
        failures += 1
    if not _expect_runtime_leak_tracking(ROOT / "tests" / "security" / "runtime_leak_tracking.dsy"):
        failures += 1
    if not _expect_file_read_boundary(ROOT / "tests" / "security" / "file_read_boundary.dsy"):
        failures += 1
    if not _expect_file_read_empty(ROOT / "tests" / "security" / "file_read_empty.dsy"):
        failures += 1
    if not _expect_net_recv_fuzz(ROOT / "tests" / "security" / "net_recv_fuzz.dsy"):
        failures += 1
    if not _expect_channel_close_recv(ROOT / "tests" / "security" / "channel_close_recv.dsy"):
        failures += 1
    return failures


def _compile_and_run(path: Path, timeout: float = 10.0) -> subprocess.CompletedProcess[str] | None:
    try:
        build_dir = _next_build_dir(path.stem)
        sanitize = os.environ.get("DAISY_SANITIZE")
        result = compile_file(path, build_dir, rt_checks=True, sanitize=sanitize)
    except RuntimeError as exc:
        print(f"unexpected failure: {path}\n{exc}")
        return None
    try:
        return subprocess.run(
            [str(result.exe_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"execution timeout: {path}")
        return None
    except OSError as exc:
        print(f"execution failed: {path}\n{exc}")
        return None


def _expect_net_recv_oversize_failure(path: Path) -> bool:
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
    generated = ROOT / "build" / f"_net_recv_oversize_{port}.dsy"
    generated.write_text(source.replace("PORT_PLACEHOLDER", str(port)), encoding="utf-8")
    completed = _compile_and_run(generated)
    thread.join(timeout=2.0)
    if completed is None:
        return False
    if completed.returncode == 0:
        print(f"expected runtime failure but succeeded: {path}")
        return False
    return True


def _expect_runtime_leak_tracking(path: Path) -> bool:
    completed = _compile_and_run(path)
    if completed is None:
        return False
    if completed.returncode != 0:
        print(f"execution failed: {path}\nexit: {completed.returncode}")
        return False
    output = completed.stdout.replace("\r\n", "\n").strip().splitlines()
    if len(output) < 3:
        print(f"unexpected output: {path}\n{completed.stdout}")
        return False
    try:
        before = int(output[0].strip())
        mid = int(output[1].strip())
        after = int(output[2].strip())
    except ValueError:
        print(f"unexpected output: {path}\n{completed.stdout}")
        return False
    if mid <= before:
        print(f"runtime tracking failed (mid <= before): {before}, {mid}, {after}")
        return False
    if after != before:
        print(f"runtime tracking failed (after != before): {before}, {mid}, {after}")
        return False
    return True


def _expect_file_read_boundary(path: Path) -> bool:
    file_path = ROOT / "build" / "security_file.bin"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if not _write_file_with_size(file_path, 8):
        return False
    completed = _compile_and_run(path)
    if completed is None:
        return False
    output = completed.stdout.replace("\r\n", "\n").strip()
    if output != "OK":
        print(f"unexpected output: {path}\n{completed.stdout}")
        return False
    max_size = 64 * 1024 * 1024
    if not _write_file_with_size(file_path, max_size + 1):
        return False
    completed = _compile_and_run(path)
    if completed is None:
        return False
    output = completed.stdout.replace("\r\n", "\n").strip()
    if output != "NULL":
        print(f"unexpected output: {path}\n{completed.stdout}")
        return False
    return True


def _expect_file_read_empty(path: Path) -> bool:
    file_path = ROOT / "build" / "security_empty.bin"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if not _write_file_with_size(file_path, 0):
        return False
    completed = _compile_and_run(path)
    if completed is None:
        return False
    output = completed.stdout.replace("\r\n", "\n").strip()
    if output != "EMPTY":
        print(f"unexpected output: {path}\n{completed.stdout}")
        return False
    return True


def _expect_net_recv_fuzz(path: Path) -> bool:
    max_read = 4 * 1024 * 1024
    sizes = [0, 1, 8, 1024, max_read - 1, max_read, max_read + 1, max_read + 1024 * 1024]
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def handler() -> None:
        try:
            for _ in sizes:
                conn, _addr = server.accept()
                _ = conn.recv(1024)
                conn.sendall(b"pong")
                conn.close()
        finally:
            server.close()

    thread = threading.Thread(target=handler, daemon=True)
    thread.start()
    for size in sizes:
        source = path.read_text(encoding="utf-8")
        generated = ROOT / "build" / f"_net_recv_fuzz_{port}_{size}.dsy"
        updated = source.replace("PORT_PLACEHOLDER", str(port)).replace("MAX_BYTES_PLACEHOLDER", str(size))
        generated.write_text(updated, encoding="utf-8")
        completed = _compile_and_run(generated)
        if completed is None:
            thread.join(timeout=2.0)
            return False
        if size <= max_read:
            if completed.returncode != 0:
                print(f"unexpected failure for size {size}: {path}")
                thread.join(timeout=2.0)
                return False
        else:
            if completed.returncode == 0:
                print(f"expected failure for size {size}: {path}")
                thread.join(timeout=2.0)
                return False
    thread.join(timeout=2.0)
    return True


def _expect_channel_close_recv(path: Path) -> bool:
    completed = _compile_and_run(path, timeout=3.0)
    if completed is None:
        return False
    if completed.returncode != 0:
        print(f"execution failed: {path}\nexit: {completed.returncode}")
        return False
    output = completed.stdout.replace("\r\n", "\n").strip()
    if output != "0":
        print(f"unexpected output: {path}\n{completed.stdout}")
        return False
    return True


def _write_file_with_size(path: Path, size: int) -> bool:
    try:
        with path.open("wb") as fp:
            if size <= 0:
                return True
            fp.seek(size - 1)
            fp.write(b"\0")
        return True
    except OSError as exc:
        print(f"file write failed: {path}\n{exc}")
        return False


def _next_build_dir(name: str) -> Path:
    base = ROOT / "build" / "security" / name
    unique = uuid.uuid4().hex
    return base / unique


if __name__ == "__main__":
    raise SystemExit(main())

