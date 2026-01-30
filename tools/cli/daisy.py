from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "compiler-bootstrap"))
sys.path.insert(0, str(ROOT / "compiler-core"))

from compiler_bootstrap.driver import compile_file  # noqa: E402
from compiler_bootstrap.formatter import format_source  # noqa: E402
from tools.lint.lint import run_lint  # noqa: E402
from tools.docgen.docgen import run_docgen  # noqa: E402
from tools.bindgen.bindgen import run_bindgen  # noqa: E402
from pkg.cargo_bridge.bridge import pkg_add  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(prog="daisy")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    build = sub.add_parser("build")
    build.add_argument("file", nargs="?", default="src/main.dsy")
    build.add_argument("--lto", action="store_true")
    build.add_argument("--emit-ir", action="store_true")
    build.add_argument("--no-rt-checks", dest="rt_checks", action="store_false")
    build.set_defaults(rt_checks=True)
    build.add_argument("--profile", action="store_true")
    build.add_argument("--sanitize", default=None)
    build.add_argument("--link", action="append", default=[])

    run = sub.add_parser("run")
    run.add_argument("file", nargs="?", default="src/main.dsy")
    run.add_argument("--emit-ir", action="store_true")
    run.add_argument("--no-rt-checks", dest="rt_checks", action="store_false")
    run.set_defaults(rt_checks=True)
    run.add_argument("--profile", action="store_true")
    run.add_argument("--sanitize", default=None)

    test = sub.add_parser("test")
    test.add_argument("--long", action="store_true")
    bench = sub.add_parser("bench")
    bench.add_argument("--json", action="store_true")
    bench.add_argument("--out", default=None)
    bench.add_argument("--runs", type=int, default=None)
    bench.add_argument("--warmup", type=int, default=None)

    sub.add_parser("build-compiler")
    sub.add_parser("build-stage1")

    sub.add_parser("lsp")

    fmt = sub.add_parser("fmt")
    fmt.add_argument("path", nargs="?", default="src")

    lint = sub.add_parser("lint")
    lint.add_argument("path", nargs="?", default="src")

    doc = sub.add_parser("doc")
    doc.add_argument("path", nargs="?", default="src")

    pkg = sub.add_parser("pkg")
    pkg_sub = pkg.add_subparsers(dest="pkg_cmd", required=True)
    pkg_add_cmd = pkg_sub.add_parser("add")
    pkg_add_cmd.add_argument("crate")

    bindgen = sub.add_parser("bindgen")
    bindgen.add_argument("mode")
    bindgen.add_argument("target")

    args = parser.parse_args()

    if args.cmd == "init":
        return _cmd_init()
    if args.cmd == "build":
        return _cmd_build(args.file, args.lto, args.link, args.emit_ir, args.rt_checks, args.profile, args.sanitize)
    if args.cmd == "run":
        return _cmd_run(args.file, args.emit_ir, args.rt_checks, args.profile, args.sanitize)
    if args.cmd == "test":
        return _cmd_test(args.long)
    if args.cmd == "bench":
        return _cmd_bench(args.json, args.out, args.runs, args.warmup)
    if args.cmd == "build-compiler":
        return _cmd_build_compiler()
    if args.cmd == "build-stage1":
        return _cmd_build_stage1()
    if args.cmd == "lsp":
        return _cmd_lsp()
    if args.cmd == "fmt":
        return _cmd_fmt(args.path)
    if args.cmd == "lint":
        return _cmd_lint(args.path)
    if args.cmd == "doc":
        return _cmd_doc(args.path)
    if args.cmd == "pkg":
        if args.pkg_cmd == "add":
            return pkg_add(Path("daisy.toml"), args.crate)
    if args.cmd == "bindgen":
        return run_bindgen(args.mode, args.target)
    return 1


def _cmd_init() -> int:
    (ROOT / "src").mkdir(exist_ok=True)
    daisy_toml = ROOT / "daisy.toml"
    if not daisy_toml.exists():
        daisy_toml.write_text(
            "\n".join(
                [
                    "[package]",
                    'name = "daisy-app"',
                    'version = "0.1.0"',
                    "",
                    "[dependencies]",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    main_src = ROOT / "src" / "main.dsy"
    if not main_src.exists():
        main_src.write_text(
            "\n".join(
                [
                    "module app",
                    "fn main() -> int:",
                    '  print "Hello, DAISY"',
                    "  return 0",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    return 0


def _cmd_build(
    file_path: str,
    lto: bool,
    link: list[str],
    emit_ir: bool,
    rt_checks: bool,
    profile: bool,
    sanitize: str | None,
) -> int:
    link_libs = [Path(p) for p in link] if link else None
    try:
        result = compile_file(
            Path(file_path),
            ROOT / "build",
            lto=lto,
            emit_ir=emit_ir,
            rt_checks=rt_checks,
            profile=profile,
            sanitize=sanitize,
            link_libs=link_libs,
        )
    except RuntimeError as exc:
        print(str(exc))
        return 1
    print(f"Built: {result.exe_path}")
    return 0


def _cmd_run(file_path: str, emit_ir: bool, rt_checks: bool, profile: bool, sanitize: str | None) -> int:
    try:
        result = compile_file(
            Path(file_path),
            ROOT / "build",
            emit_ir=emit_ir,
            rt_checks=rt_checks,
            profile=profile,
            sanitize=sanitize,
        )
    except RuntimeError as exc:
        print(str(exc))
        return 1
    exe = result.exe_path
    if sys.platform.startswith("win"):
        exe = exe.with_suffix(".exe")
    subprocess.check_call([str(exe)])
    return 0


def _cmd_test(is_long: bool) -> int:
    if is_long:
        return subprocess.call([sys.executable, str(ROOT / "tests" / "long" / "run_long_tests.py")])
    return subprocess.call([sys.executable, str(ROOT / "tests" / "run_tests.py")])


def _cmd_bench(as_json: bool, out: str | None, runs: int | None, warmup: int | None) -> int:
    cmd = [sys.executable, str(ROOT / "bench" / "bench.py")]
    if as_json:
        cmd.append("--json")
    if out:
        cmd += ["--out", out]
    if runs is not None:
        cmd += ["--runs", str(runs)]
    if warmup is not None:
        cmd += ["--warmup", str(warmup)]
    return subprocess.call(cmd)
def _cmd_lsp() -> int:
    return subprocess.call([sys.executable, str(ROOT / "tools" / "lsp" / "server.py")])


def _cmd_fmt(path: str) -> int:
    p = Path(path)
    files = list(p.rglob("*.dsy")) if p.is_dir() else [p]
    for file in files:
        formatted = format_source(file.read_text(encoding="utf-8"))
        file.write_text(formatted, encoding="utf-8")
    return 0


def _cmd_lint(path: str) -> int:
    return run_lint(Path(path))


def _cmd_doc(path: str) -> int:
    return run_docgen(Path(path))


def _cmd_build_compiler() -> int:
    compiler_src = ROOT / "compiler-daisy" / "compiler.dsy"
    result = compile_file(compiler_src, ROOT / "build")
    print(f"Built compiler: {result.exe_path}")
    return 0


def _cmd_build_stage1() -> int:
    compiler_src = ROOT / "compiler-daisy" / "compiler.dsy"
    result = compile_file(compiler_src, ROOT / "build")
    exe = result.exe_path
    if sys.platform.startswith("win"):
        exe = exe.with_suffix(".exe")
    subprocess.check_call([str(exe)], cwd=str(ROOT))
    out_path = ROOT / "build" / "main.c"
    if not out_path.exists():
        print("Stage1 did not emit build/main.c")
        return 1
    print(f"Stage1 output: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


