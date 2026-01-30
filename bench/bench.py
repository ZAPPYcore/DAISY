from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "compiler-bootstrap"))
sys.path.insert(0, str(ROOT / "compiler-core"))

from compiler_bootstrap import driver  # noqa: E402
from compiler_bootstrap.driver import compile_file  # noqa: E402


@dataclass
class BenchCase:
    name: str
    daisy: Path
    c: Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="write JSON results")
    parser.add_argument("--out", default=str(ROOT / "bench" / "results.json"))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    args = parser.parse_args()

    benches = [
        BenchCase("sum_loop", ROOT / "bench" / "daisy" / "sum_loop.dsy", ROOT / "bench" / "c" / "sum_loop.c"),
        BenchCase("fib_iter", ROOT / "bench" / "daisy" / "fib_iter.dsy", ROOT / "bench" / "c" / "fib_iter.c"),
        BenchCase("vec_push", ROOT / "bench" / "daisy" / "vec_push.dsy", ROOT / "bench" / "c" / "vec_push.c"),
    ]
    results: list[tuple[str, float, float]] = []
    previous = None
    if args.json:
        out_path = Path(args.out)
        if out_path.exists():
            try:
                previous = json.loads(out_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                previous = None
    for bench in benches:
        build_dir = ROOT / "bench" / "build" / bench.name / str(time.time_ns())
        build_dir.mkdir(parents=True, exist_ok=True)
        daisy_exe = _build_daisy(bench.daisy, build_dir)
        c_exe = _build_c(bench.c, build_dir)
        daisy_time = _run_bench(daisy_exe, warmup=args.warmup, runs=args.runs)
        c_time = _run_bench(c_exe, warmup=args.warmup, runs=args.runs)
        results.append((bench.name, daisy_time, c_time))

    print("benchmark results (seconds, lower is better)")
    for name, daisy_time, c_time in results:
        ratio = daisy_time / c_time if c_time > 0 else 0.0
        print(f"{name}: daisy={daisy_time:.6f}s c={c_time:.6f}s ratio={ratio:.2f}x")
    if args.json:
        payload = {
            "runs": args.runs,
            "warmup": args.warmup,
            "results": [
                {"name": name, "daisy": daisy_time, "c": c_time, "ratio": (daisy_time / c_time if c_time else 0.0)}
                for name, daisy_time, c_time in results
            ],
        }
        Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        _compare_previous(previous, payload)
    return 0


def _build_daisy(path: Path, build_dir: Path) -> Path:
    module_name = _module_name(path)
    if module_name:
        exe_path = build_dir / module_name
        if sys.platform.startswith("win"):
            exe_path = exe_path.with_suffix(".exe")
        if exe_path.exists():
            try:
                exe_path.unlink()
            except OSError:
                pass
    result = compile_file(path, build_dir)
    exe = result.exe_path
    if sys.platform.startswith("win"):
        exe = exe.with_suffix(".exe")
    return exe


def _build_c(path: Path, build_dir: Path) -> Path:
    cc = driver._find_cc()
    if cc is None:
        raise RuntimeError("No C compiler found for benchmarks.")
    exe_name = f"{path.stem}_c"
    exe_path = build_dir / exe_name
    if sys.platform.startswith("win"):
        exe_path = exe_path.with_suffix(".exe")
    if cc == "cl":
        cmd = ["cl", "/nologo", "/O2", str(path), f"/Fe:{exe_path}"]
        subprocess.check_call(cmd)
        return exe_path
    if cc == "msvc":
        vcvars = driver._find_vcvarsall()
        if not vcvars:
            raise RuntimeError("MSVC found but vcvarsall.bat not located")
        vcvars = vcvars.strip('"')
        cl_cmd = ["cl", "/nologo", "/O2", str(path), f"/Fe:{exe_path}"]
        cmd_str = f'call "{vcvars}" x64 && ' + " ".join(cl_cmd)
        subprocess.check_call(cmd_str, shell=True)
        return exe_path
    cmd = [cc, "-O2", str(path), "-o", str(exe_path)]
    subprocess.check_call(cmd)
    return exe_path


def _run_bench(exe: Path, warmup: int, runs: int) -> float:
    for _ in range(warmup):
        subprocess.check_call([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        subprocess.check_call([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        times.append(time.perf_counter() - start)
    return min(times) if times else 0.0


def _module_name(path: Path) -> Optional[str]:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("module "):
                return stripped.split(" ", 1)[1].strip()
            if stripped.startswith("모듈 "):
                return stripped.split(" ", 1)[1].strip()
            return None
    except OSError:
        return None


def _compare_previous(previous: Optional[dict], current: dict) -> None:
    if not previous:
        return
    prev_map = {item.get("name"): item for item in previous.get("results", []) if isinstance(item, dict)}
    for item in current.get("results", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        prev = prev_map.get(name)
        if not prev:
            continue
        prev_ratio = prev.get("ratio")
        curr_ratio = item.get("ratio")
        if isinstance(prev_ratio, (int, float)) and isinstance(curr_ratio, (int, float)):
            if curr_ratio > prev_ratio * 1.2:
                print(f"warning: {name} regression {prev_ratio:.2f}x -> {curr_ratio:.2f}x")


if __name__ == "__main__":
    raise SystemExit(main())


