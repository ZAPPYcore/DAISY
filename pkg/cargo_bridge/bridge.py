from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict


def pkg_add(toml_path: Path, crate: str) -> int:
    data = toml_path.read_text(encoding="utf-8") if toml_path.exists() else ""
    deps = _parse_deps(data)
    deps[crate] = {"version": "*", "source": "crates.io"}
    toml_path.write_text(_render_toml(deps), encoding="utf-8")
    lock_path = toml_path.parent / "daisy.lock"
    lock_path.write_text(_render_lock(deps), encoding="utf-8")
    print(f"pkg: added {crate}")
    return 0


def _parse_deps(data: str) -> Dict[str, Dict[str, str]]:
    deps: Dict[str, Dict[str, str]] = {}
    in_deps = False
    for line in data.splitlines():
        if line.strip() == "[dependencies]":
            in_deps = True
            continue
        if line.startswith("[") and line.strip() != "[dependencies]":
            in_deps = False
        if in_deps and "=" in line:
            name, rest = line.split("=", 1)
            deps[name.strip()] = {"version": rest.strip().strip('"')}
    return deps


def _render_toml(deps: Dict[str, Dict[str, str]]) -> str:
    lines = ["[package]", 'name = "daisy-app"', 'version = "0.1.0"', "", "[dependencies]"]
    for name, meta in deps.items():
        version = meta.get("version", "*")
        lines.append(f'{name} = "{version}"')
    lines.append("")
    return "\n".join(lines)


def _render_lock(deps: Dict[str, Dict[str, str]]) -> str:
    lines = ["# daisy.lock", ""]
    for name in deps.keys():
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
        lines.append(f"{name} = \"{digest}\"")
    lines.append("")
    return "\n".join(lines)


