from __future__ import annotations

import glob
import hashlib
import json
import os
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "compiler-core"))

from compiler_bootstrap import parser  # noqa: E402
from compiler_bootstrap import typecheck  # noqa: E402
from compiler_bootstrap import borrowcheck  # noqa: E402
from compiler_bootstrap import irgen  # noqa: E402
from compiler_bootstrap import optimize  # noqa: E402
from compiler_bootstrap import codegen_c  # noqa: E402
from compiler_bootstrap import ir_validate  # noqa: E402
from compiler_core import abi, ast, types  # noqa: E402
from compiler_core.diagnostics import format_diagnostic  # noqa: E402


COMPILER_CACHE_REV = "2026-01-29-stdlib-nll-sanitize-14"


@dataclass
class CompileResult:
    c_path: Path
    exe_path: Path


def compile_file(
    source_path: Path,
    build_dir: Path,
    lto: bool = False,
    emit_ir: bool = False,
    rt_checks: bool = False,
    profile: bool = False,
    sanitize: Optional[str] = None,
    link_libs: Optional[List[Path]] = None,
) -> CompileResult:
    return compile_project(
        source_path,
        build_dir,
        lto=lto,
        emit_ir=emit_ir,
        rt_checks=rt_checks,
        profile=profile,
        sanitize=sanitize,
        link_libs=link_libs,
    )


def compile_project(
    entry_path: Path,
    build_dir: Path,
    lto: bool = False,
    emit_ir: bool = False,
    rt_checks: bool = False,
    profile: bool = False,
    sanitize: Optional[str] = None,
    link_libs: Optional[List[Path]] = None,
) -> CompileResult:
    entry_path = entry_path.resolve()
    profile_data: dict[str, dict[str, float]] = {}
    overall_start = time.perf_counter()
    manifest_path, manifest_data = _load_manifest(entry_path)
    _check_dependency_versions(manifest_path, manifest_data)
    _check_dependency_abi(manifest_path, manifest_data)
    workspace_paths = _workspace_search_paths(manifest_path, manifest_data)
    search_paths = _dependency_search_paths(manifest_path, manifest_data) + workspace_paths
    sources = _load_project(entry_path, search_paths)
    sigs = _collect_signatures(sources)
    generic_funcs = _collect_generic_funcs(sources)
    type_defs = _collect_type_defs(sources)
    c_paths: List[Path] = []
    exe_name = sources[entry_path].name
    module_map = {module.name: path for path, module in sources.items()}
    module_sources = {module.name: path.read_text(encoding="utf-8") for path, module in sources.items()}
    dep_graph = _module_dep_graph(sources, module_map)
    combined_hashes = _combined_module_hashes(module_sources, dep_graph)

    def compile_one(path: Path, module: ast.Module) -> tuple[Path, dict[str, float]]:
        timings: dict[str, float] = {}
        source = module_sources[module.name]
        ext_sigs = _external_sigs_for_module(module.name, sigs)
        t0 = time.perf_counter()
        ext_types, ext_structs, ext_enums = _external_types_for_module(module.name, type_defs)
        ext_generic_funcs = _external_generic_funcs_for_module(module.name, generic_funcs)
        checker = typecheck.TypeChecker(
            external_sigs=ext_sigs,
            external_types=ext_types,
            external_structs=ext_structs,
            external_enums=ext_enums,
            external_generic_funcs=ext_generic_funcs,
        )
        type_info = checker.check_module(module)
        timings["typecheck"] = time.perf_counter() - t0
        if checker.errors:
            raise RuntimeError("\n".join(format_diagnostic(e, source) for e in checker.errors))
        if checker.impl_functions or checker.specialized_functions:
            module = ast.Module(
                name=module.name,
                body=module.body + checker.impl_functions + checker.specialized_functions,
                span=module.span,
            )
        t0 = time.perf_counter()
        borrow = borrowcheck.BorrowChecker(type_info)
        borrow.check_module(module)
        timings["borrowcheck"] = time.perf_counter() - t0
        if borrow.errors:
            raise RuntimeError("\n".join(format_diagnostic(e, source) for e in borrow.errors))
        _emit_unsafe_report(module, build_dir)
        cache = _load_build_cache(build_dir, module.name)
        module_hash = combined_hashes.get(module.name, _module_hash(source))
        c_path = build_dir / f"{module.name}.c"
        abi_path = build_dir / f"{module.name}.abi.json"
        if cache and cache.get("hash") == module_hash and c_path.exists() and abi_path.exists():
            return c_path, timings
        t0 = time.perf_counter()
        ir_module = irgen.IRGen(
            struct_defs=checker.struct_defs,
            enum_defs=checker.enum_defs,
            expr_types=type_info.expr_types,
        ).lower_module(module)
        timings["irgen"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        optimized = optimize.Optimizer().run(ir_module)
        timings["optimize"] = time.perf_counter() - t0
        _check_abi_compat(optimized, build_dir)
        ir_validate.validate_module(optimized)
        extern_map = _extern_signature_map(ext_sigs)
        t0 = time.perf_counter()
        c_code = codegen_c.CCodegen().emit(optimized, extern_signatures=extern_map)
        timings["codegen"] = time.perf_counter() - t0
        build_dir.mkdir(parents=True, exist_ok=True)
        c_path.write_text(c_code, encoding="utf-8-sig")
        if emit_ir:
            (build_dir / f"{module.name}.ir.txt").write_text(_format_ir(optimized), encoding="utf-8")
        _emit_abi_manifest(optimized, build_dir)
        _write_build_cache(build_dir, module.name, module_hash)
        return c_path, timings

    items = list(sources.items())
    if len(items) <= 1:
        for path, module in items:
            c_path, timings = compile_one(path, module)
            c_paths.append(c_path)
            profile_data[module.name] = timings
    else:
        workers = max(1, os.cpu_count() or 1)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {pool.submit(compile_one, path, module): module.name for path, module in items}
            for future in as_completed(future_map):
                c_path, timings = future.result()
                c_paths.append(c_path)
                profile_data[future_map[future]] = timings
    exe_path = build_dir / exe_name
    link_start = time.perf_counter()
    _build_c(c_paths, exe_path, lto=lto, rt_checks=rt_checks, sanitize=sanitize, link_libs=link_libs)
    link_time = time.perf_counter() - link_start
    if profile:
        build_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "total": time.perf_counter() - overall_start,
            "link": link_time,
            "modules": profile_data,
        }
        (build_dir / "profile.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return CompileResult(c_path=c_paths[0], exe_path=exe_path)


def _build_c(
    c_paths: List[Path],
    exe_path: Path,
    lto: bool = False,
    rt_checks: bool = False,
    sanitize: Optional[str] = None,
    link_libs: Optional[List[Path]] = None,
) -> None:
    cc = _find_cc()
    if cc is None:
        raise RuntimeError(
            "No C compiler found (clang, gcc, or MSVC cl required). "
            "On Windows, install Visual Studio Build Tools and rerun."
        )
    rt_c = ROOT / "runtime" / "rt.c"
    if cc == "cl":
        cmd = [
            "cl",
            "/nologo",
            "/std:c11",
            "/O2",
            f"/I{ROOT / 'runtime'}",
            "/DDAISY_RT_CHECKS" if rt_checks else "",
            "/fsanitize=address" if sanitize else "",
            *[str(p) for p in c_paths],
            str(rt_c),
            f"/Fe:{exe_path}.exe",
        ]
        cmd = [c for c in cmd if c]
        if link_libs:
            cmd += [str(lib) for lib in link_libs]
        if sys.platform == "win32":
            cmd.append("ws2_32.lib")
        subprocess.check_call(cmd)
        return
    if cc == "msvc":
        vcvars = _find_vcvarsall()
        if not vcvars:
            raise RuntimeError("MSVC found but vcvarsall.bat not located")
        vcvars = vcvars.strip('"')
        cl_cmd = [
            "cl",
            "/nologo",
            "/std:c11",
            "/O2",
            "/utf-8",
            f"/I{ROOT / 'runtime'}",
            "/DDAISY_RT_CHECKS" if rt_checks else "",
            "/fsanitize=address" if sanitize else "",
            *[str(p) for p in c_paths],
            str(rt_c),
            f"/Fe:{exe_path}.exe",
        ]
        cl_cmd = [c for c in cl_cmd if c]
        if link_libs:
            cl_cmd += [str(lib) for lib in link_libs]
        if sys.platform == "win32":
            cl_cmd.append("ws2_32.lib")
        cmd_str = f'call "{vcvars}" x64 && ' + " ".join(cl_cmd)
        subprocess.check_call(cmd_str, shell=True)
        return
    flags: List[str] = ["-std=c11", "-O2"]
    if lto:
        flags.append("-flto")
    if rt_checks:
        flags.append("-DDAISY_RT_CHECKS")
    if sanitize:
        flags.append(f"-fsanitize={sanitize}")
        flags.append("-fno-omit-frame-pointer")
        flags.append("-g")
    cmd = [cc, *[str(p) for p in c_paths], str(rt_c), "-o", str(exe_path), "-I", str(ROOT / "runtime")] + flags
    if link_libs:
        for lib in link_libs:
            cmd.append(str(lib))
    if sys.platform == "win32":
        cmd.append("-lws2_32")
    subprocess.check_call(cmd)


def _collect_signatures(modules: Dict[Path, "ast.Module"]) -> Dict[str, typecheck.FuncSig]:
    sigs: Dict[str, typecheck.FuncSig] = {}
    resolver = typecheck.TypeChecker()
    for module in modules.values():
        for stmt in module.body:
            if isinstance(stmt, ast.FunctionDef):
                if not stmt.is_public:
                    continue
                params = [resolver._resolve_type(p.type_ref) for p in stmt.params]
                sigs[f"{module.name}.{stmt.name}"] = typecheck.FuncSig(
                    params=params,
                    returns=resolver._resolve_type(stmt.return_type),
                )
            elif isinstance(stmt, ast.ExternFunctionDef):
                if not stmt.is_public:
                    continue
                params = [resolver._resolve_type(p.type_ref) for p in stmt.params]
                sigs[f"{module.name}.{stmt.name}"] = typecheck.FuncSig(
                    params=params,
                    returns=resolver._resolve_type(stmt.return_type),
                )
    return sigs


def _collect_generic_funcs(modules: Dict[Path, "ast.Module"]) -> Dict[str, ast.FunctionDef]:
    funcs: Dict[str, ast.FunctionDef] = {}
    for module in modules.values():
        for stmt in module.body:
            if isinstance(stmt, ast.FunctionDef) and stmt.type_params:
                funcs[f"{module.name}.{stmt.name}"] = stmt
    return funcs


def _collect_type_defs(
    modules: Dict[Path, "ast.Module"],
) -> Tuple[Dict[str, types.Type], Dict[str, List[tuple[str, types.Type]]], Dict[str, List[tuple[str, Optional[types.Type]]]]]:
    type_map: Dict[str, types.Type] = {}
    struct_map: Dict[str, List[tuple[str, types.Type]]] = {}
    enum_map: Dict[str, List[tuple[str, Optional[types.Type]]]] = {}
    resolver = typecheck.TypeChecker()
    for module in modules.values():
        for stmt in module.body:
            if isinstance(stmt, ast.StructDef):
                if not stmt.is_public:
                    continue
                fields: List[tuple[str, types.Type]] = []
                is_copy = True
                for field in stmt.fields:
                    t = resolver._resolve_type(field.type_ref)
                    fields.append((field.name, t))
                    if not t.is_copy:
                        is_copy = False
                type_map[f"{module.name}.{stmt.name}"] = types.Type(name=stmt.name, is_copy=is_copy)
                struct_map[f"{module.name}.{stmt.name}"] = fields
            elif isinstance(stmt, ast.EnumDef):
                if not stmt.is_public:
                    continue
                cases: List[tuple[str, Optional[types.Type]]] = []
                for case in stmt.cases:
                    payload = resolver._resolve_type(case.payload) if case.payload else None
                    cases.append((case.name, payload))
                type_map[f"{module.name}.{stmt.name}"] = types.Type(name=stmt.name, is_copy=False)
                enum_map[f"{module.name}.{stmt.name}"] = cases
    return type_map, struct_map, enum_map


def _external_types_for_module(
    module_name: str,
    type_defs: Tuple[
        Dict[str, types.Type],
        Dict[str, List[tuple[str, types.Type]]],
        Dict[str, List[tuple[str, Optional[types.Type]]]],
    ],
) -> Tuple[Dict[str, types.Type], Dict[str, List[tuple[str, types.Type]]], Dict[str, List[tuple[str, Optional[types.Type]]]]]:
    type_map, struct_map, enum_map = type_defs
    ext_types: Dict[str, types.Type] = {}
    ext_structs: Dict[str, List[tuple[str, types.Type]]] = {}
    ext_enums: Dict[str, List[tuple[str, Optional[types.Type]]]] = {}
    for name, t in type_map.items():
        if not name.startswith(f"{module_name}."):
            ext_types[name] = t
    for name, fields in struct_map.items():
        if not name.startswith(f"{module_name}."):
            ext_structs[name] = fields
    for name, cases in enum_map.items():
        if not name.startswith(f"{module_name}."):
            ext_enums[name] = cases
    return ext_types, ext_structs, ext_enums


def _external_sigs_for_module(module_name: str, sigs: Dict[str, typecheck.FuncSig]) -> Dict[str, typecheck.FuncSig]:
    externals: Dict[str, typecheck.FuncSig] = {}
    for name, sig in sigs.items():
        if not name.startswith(f"{module_name}."):
            externals[name] = sig
    return externals


def _external_generic_funcs_for_module(
    module_name: str,
    funcs: Dict[str, ast.FunctionDef],
) -> Dict[str, ast.FunctionDef]:
    externals: Dict[str, ast.FunctionDef] = {}
    for name, func in funcs.items():
        if not name.startswith(f"{module_name}."):
            externals[name] = func
    return externals


def _extern_signature_map(sigs: Dict[str, typecheck.FuncSig]) -> Dict[str, Tuple[str, List[str], str]]:
    extern_map: Dict[str, Tuple[str, List[str], str]] = {}
    for name, sig in sigs.items():
        module_name, fn_name = name.split(".", 1)
        params = [t.name for t in sig.params]
        extern_map[name] = (module_name, params, sig.returns.name)
    return extern_map


def _load_project(entry_path: Path, search_paths: Optional[List[Path]] = None) -> Dict[Path, "ast.Module"]:
    entry_path = entry_path.resolve()
    modules: Dict[Path, "ast.Module"] = {}
    name_to_path: Dict[str, Path] = {}
    stack: List[Path] = [entry_path]
    while stack:
        path = stack.pop()
        if path in modules:
            continue
        source = path.read_text(encoding="utf-8")
        module = parser.parse(source)
        modules[path] = module
        name_to_path[module.name] = path
        for stmt in module.body:
            if isinstance(stmt, ast.Import):
                import_path = _resolve_module_path(stmt.module, path.parent, search_paths or [])
                if import_path not in modules:
                    stack.append(import_path)
    return modules


def _resolve_module_path(name: str, base_dir: Path, search_paths: List[Path]) -> Path:
    candidates: List[Path] = []
    for prefix in search_paths:
        candidates.append(prefix / f"{name}.dsy")
    candidates.extend(
        [
            base_dir / f"{name}.dsy",
            ROOT / "src" / f"{name}.dsy",
            ROOT / "stdlib" / f"{name}.dsy",
            ROOT / "examples" / f"{name}.dsy",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError(f"Module not found: {name}")


def _load_manifest(entry_path: Path) -> tuple[Optional[Path], dict]:
    manifest = _find_manifest(entry_path)
    if not manifest:
        return None, {}
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return manifest, {}
    return manifest, data


def _find_manifest(entry_path: Path) -> Optional[Path]:
    cur = entry_path if entry_path.is_dir() else entry_path.parent
    while True:
        candidate = cur / "daisy.toml"
        if candidate.exists():
            return candidate
        if cur == cur.parent:
            return None
        cur = cur.parent


def _dependency_search_paths(manifest: Optional[Path], data: dict) -> List[Path]:
    if not manifest or not data:
        return []
    deps = data.get("dependencies", {})
    if not isinstance(deps, dict):
        return []
    paths: List[Path] = []
    for _, spec in deps.items():
        dep_path, _ = _dep_spec_to_path_req(manifest, spec)
        if dep_path is None:
            continue
        if not dep_path.is_absolute():
            dep_path = (manifest.parent / dep_path).resolve()
        paths.append(dep_path / "src")
        paths.append(dep_path)
    return paths


def _workspace_search_paths(manifest: Optional[Path], data: dict) -> List[Path]:
    if not manifest or not data:
        return []
    workspace = data.get("workspace", {})
    if not isinstance(workspace, dict):
        return []
    members = workspace.get("members", [])
    if not isinstance(members, list):
        return []
    paths: List[Path] = []
    for member in members:
        if not isinstance(member, str):
            continue
        if any(ch in member for ch in ("*", "?", "[")):
            pattern = str((manifest.parent / member).resolve())
            matches = [Path(p) for p in glob.glob(pattern)]
        else:
            matches = [(manifest.parent / member).resolve()]
        for member_path in matches:
            if not member_path.exists():
                continue
            paths.append(member_path / "src")
            paths.append(member_path)
    return paths


def _module_hash(source: str) -> str:
    payload = f"{abi.ABI_VERSION_MAJOR}.{abi.ABI_VERSION_MINOR}\n{COMPILER_CACHE_REV}\n{source}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _module_dep_graph(
    modules: Dict[Path, "ast.Module"],
    module_map: Dict[str, Path],
) -> Dict[str, List[str]]:
    graph: Dict[str, List[str]] = {}
    for path, module in modules.items():
        deps: List[str] = []
        for stmt in module.body:
            if isinstance(stmt, ast.Import):
                name = stmt.module
                if name in module_map:
                    deps.append(name)
        graph[module.name] = deps
    return graph


def _combined_module_hashes(
    module_sources: Dict[str, str],
    dep_graph: Dict[str, List[str]],
) -> Dict[str, str]:
    base_hashes = {name: _module_hash(src) for name, src in module_sources.items()}
    combined: Dict[str, str] = {}

    def visit(name: str) -> str:
        if name in combined:
            return combined[name]
        deps = dep_graph.get(name, [])
        dep_hashes = [visit(dep) for dep in deps if dep in base_hashes]
        payload = base_hashes.get(name, "") + "".join(sorted(dep_hashes))
        combined[name] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return combined[name]

    for name in base_hashes:
        visit(name)
    return combined


def _load_build_cache(build_dir: Path, module_name: str) -> Optional[dict]:
    cache_path = build_dir / ".cache" / f"{module_name}.json"
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _write_build_cache(build_dir: Path, module_name: str, module_hash: str) -> None:
    cache_dir = build_dir / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{module_name}.json"
    cache_path.write_text(json.dumps({"hash": module_hash}, indent=2), encoding="utf-8")


def _emit_unsafe_report(module: ast.Module, build_dir: Path) -> None:
    unsafe_entries: List[str] = []

    def walk_stmts(stmts: List[ast.Stmt]) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.UnsafeBlock):
                reason = stmt.reason or "missing"
                if stmt.span:
                    unsafe_entries.append(f"L{stmt.span.line_start}:{stmt.span.column_start} {reason}")
                else:
                    unsafe_entries.append(f"L?:? {reason}")
                walk_stmts(stmt.body)
            elif isinstance(stmt, ast.FunctionDef):
                walk_stmts(stmt.body)
            elif isinstance(stmt, ast.If):
                walk_stmts(stmt.body)
            elif isinstance(stmt, ast.Repeat):
                walk_stmts(stmt.body)
            elif isinstance(stmt, ast.While):
                walk_stmts(stmt.body)

    walk_stmts(module.body)
    if not unsafe_entries:
        return
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / f"{module.name}.unsafe.log").write_text(
        "\n".join(["module: " + module.name, *unsafe_entries, ""]),
        encoding="utf-8",
    )


def _format_ir(ir_module: "ir.IRModule") -> str:
    lines: List[str] = [f"module {ir_module.name}"]
    for ext in ir_module.externs:
        params = ", ".join([f"{p.name}:{p.type_name}" for p in ext.params])
        lines.append(f"extern {ext.name}({params}) -> {ext.return_type}")
    for func in ir_module.functions:
        params = ", ".join([f"{p.name}:{p.type_name}" for p in func.params])
        lines.append(f"fn {func.name}({params}) -> {func.return_type}:")
        for block in func.blocks:
            lines.append(f"  block {block.label}:")
            for instr in block.instructions:
                args = ", ".join(instr.args)
                if instr.result:
                    type_suffix = f":{instr.type_name}" if instr.type_name else ""
                    lines.append(f"    {instr.result}{type_suffix} = {instr.op} {args}")
                else:
                    lines.append(f"    {instr.op} {args}")
    return "\n".join(lines) + "\n"


def _dep_spec_to_path_req(manifest: Path, spec: object) -> tuple[Optional[Path], Optional[str]]:
    if isinstance(spec, str):
        return Path(spec), None
    if isinstance(spec, dict):
        path = spec.get("path")
        version = spec.get("version")
        if isinstance(path, str):
            return Path(path), version if isinstance(version, str) else None
    return None, None


def _check_dependency_versions(manifest: Optional[Path], data: dict) -> None:
    if not manifest or not data:
        return
    deps = data.get("dependencies", {})
    if not isinstance(deps, dict):
        return
    for dep_name, spec in deps.items():
        dep_path, version_req = _dep_spec_to_path_req(manifest, spec)
        if dep_path is None:
            continue
        if not dep_path.is_absolute():
            dep_path = (manifest.parent / dep_path).resolve()
        dep_manifest = dep_path / "daisy.toml"
        if not dep_manifest.exists():
            raise RuntimeError(f"Dependency manifest not found: {dep_manifest}")
        dep_data = tomllib.loads(dep_manifest.read_text(encoding="utf-8"))
        if not isinstance(dep_data, dict):
            raise RuntimeError(f"Invalid dependency manifest: {dep_manifest}")
        dep_pkg = dep_data.get("package", {})
        if not isinstance(dep_pkg, dict):
            raise RuntimeError(f"Dependency manifest missing [package]: {dep_manifest}")
        dep_version = dep_pkg.get("version")
        dep_pkg_name = dep_pkg.get("name")
        if isinstance(dep_pkg_name, str) and dep_name != dep_pkg_name:
            raise RuntimeError(f"Dependency name mismatch: {dep_name} != {dep_pkg_name}")
        if version_req:
            if not isinstance(dep_version, str):
                raise RuntimeError(f"Dependency version missing for {dep_name}")
            if not _satisfies_version(dep_version, version_req):
                raise RuntimeError(
                    f"Dependency version mismatch for {dep_name}: required {version_req}, found {dep_version}"
                )


def _check_dependency_abi(manifest: Optional[Path], data: dict) -> None:
    if not manifest or not data:
        return
    deps = data.get("dependencies", {})
    if not isinstance(deps, dict):
        return
    for dep_name, spec in deps.items():
        dep_path, _ = _dep_spec_to_path_req(manifest, spec)
        if dep_path is None:
            continue
        if not dep_path.is_absolute():
            dep_path = (manifest.parent / dep_path).resolve()
        build_dir = dep_path / "build"
        if not build_dir.exists():
            continue
        for abi_path in build_dir.glob("*.abi.json"):
            abi_data = json.loads(abi_path.read_text(encoding="utf-8"))
            abi_version = abi_data.get("abi_version", {"major": abi.ABI_VERSION_MAJOR, "minor": 0})
            if isinstance(abi_version, int):
                abi_major = abi_version
            else:
                abi_major = abi_version.get("major", 0)
            if abi_major != abi.ABI_VERSION_MAJOR:
                raise RuntimeError(
                    f"Dependency ABI major mismatch for {dep_name}: {abi_major} != {abi.ABI_VERSION_MAJOR}"
                )


def _parse_semver(value: str) -> Optional[tuple[int, int, int]]:
    parts = value.split(".")
    if not parts or not all(p.isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def _satisfies_version(actual: str, req: str) -> bool:
    act = _parse_semver(actual)
    if act is None:
        return False
    if req.startswith("^"):
        base = _parse_semver(req[1:])
        if base is None:
            return False
        if act[0] != base[0]:
            return False
        return act >= base
    base = _parse_semver(req)
    if base is None:
        return False
    return act == base


def _find_cc() -> Optional[str]:
    for name in ("clang", "gcc", "cl"):
        if _which(name):
            return name
    if os.name == "nt" and _find_vcvarsall():
        return "msvc"
    return None


def _find_vcvarsall() -> Optional[str]:
    if os.name != "nt":
        return None
    vswhere = _find_vswhere()
    if not vswhere:
        return None
    try:
        output = subprocess.check_output(
            [vswhere, "-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return None
    if not output:
        return None
    candidate = Path(output) / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
    if candidate.exists():
        return str(candidate)
    return None


def _find_vswhere() -> Optional[str]:
    pf86 = os.environ.get("ProgramFiles(x86)", "")
    candidate = Path(pf86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if candidate.exists():
        return str(candidate)
    return None


def _emit_abi_manifest(ir_module: "ir.IRModule", build_dir: Path) -> None:
    entries = []
    for func in ir_module.functions:
        if func.name == "main":
            continue
        params = [p.type_name for p in func.params]
        entries.append(
            {
                "name": func.name,
                "symbol": abi.mangle(ir_module.name, func.name),
                "params": params,
                "return": func.return_type,
                "sig": abi.signature_hash(params, func.return_type),
            }
        )
    for ext in ir_module.externs:
        params = [p.type_name for p in ext.params]
        entries.append(
            {
                "name": ext.name,
                "symbol": ext.name,
                "params": params,
                "return": ext.return_type,
                "sig": abi.signature_hash(params, ext.return_type),
                "extern": True,
            }
        )
    manifest = {"module": ir_module.name, "abi_version": abi.version_dict(), "functions": entries}
    (build_dir / f"{ir_module.name}.abi.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def _check_abi_compat(ir_module: "ir.IRModule", build_dir: Path) -> None:
    manifest_path = build_dir / f"{ir_module.name}.abi.json"
    if not manifest_path.exists():
        return
    previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    prev_funcs = {f["name"]: f for f in previous.get("functions", [])}
    prev_version = previous.get("abi_version", {"major": abi.ABI_VERSION_MAJOR, "minor": 0})
    if isinstance(prev_version, int):
        prev_major = prev_version
        prev_minor = 0
    else:
        prev_major = prev_version.get("major", 0)
        prev_minor = prev_version.get("minor", 0)
    if prev_major != abi.ABI_VERSION_MAJOR:
        return
    if abi.ABI_VERSION_MINOR < prev_minor:
        raise RuntimeError(
            f"ABI minor regression: {prev_minor} -> {abi.ABI_VERSION_MINOR}. "
            "Increase minor or regenerate with migration."
        )
    current_funcs = []
    for func in ir_module.functions:
        if func.name == "main":
            continue
        params = [p.type_name for p in func.params]
        current_funcs.append(
            {
                "name": func.name,
                "symbol": abi.mangle(ir_module.name, func.name),
                "params": params,
                "return": func.return_type,
                "sig": abi.signature_hash(params, func.return_type),
            }
        )
    for ext in ir_module.externs:
        params = [p.type_name for p in ext.params]
        current_funcs.append(
            {
                "name": ext.name,
                "symbol": ext.name,
                "params": params,
                "return": ext.return_type,
                "sig": abi.signature_hash(params, ext.return_type),
                "extern": True,
            }
        )
    errors = []
    current_names = {f["name"] for f in current_funcs}
    for name, prev in prev_funcs.items():
        if name not in current_names:
            errors.append(f"ABI removed function: {name}")
    for func in current_funcs:
        prev = prev_funcs.get(func["name"])
        if prev and prev.get("sig") != func["sig"]:
            errors.append(f"ABI mismatch for {func['name']}: {prev.get('sig')} -> {func['sig']}")
    added = [f["name"] for f in current_funcs if f["name"] not in prev_funcs]
    if added and abi.ABI_VERSION_MINOR == prev_minor:
        errors.append("ABI additions require minor version bump: " + ", ".join(added))
    if errors:
        _write_migration_log(build_dir, ir_module.name, errors, added)
        raise RuntimeError("ABI compatibility check failed:\n" + "\n".join(errors))
    if added:
        _write_migration_log(build_dir, ir_module.name, [], added)


def _write_migration_log(build_dir: Path, module_name: str, errors: List[str], added: List[str]) -> None:
    lines = [f"module: {module_name}"]
    if errors:
        lines.append("breaking_changes:")
        lines.extend(f"- {e}" for e in errors)
    if added:
        lines.append("added_functions:")
        lines.extend(f"- {name}" for name in added)
    (build_dir / f"{module_name}.abi.migration.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _which(name: str) -> Optional[str]:
    for path in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(path) / (name + ".exe" if os.name == "nt" else name)
        if candidate.exists():
            return str(candidate)
    return None


