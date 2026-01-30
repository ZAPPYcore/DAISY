from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older Python
    import tomli as tomllib  # type: ignore


ROOT = Path(__file__).resolve().parents[2]
IGNORE_DIRS = {".git", "__pycache__", "build", "target"}
IGNORE_EXTS = {".obj", ".exe", ".pdb", ".log", ".tmp"}


def main() -> int:
    manifest = ROOT / "daisy.toml"
    lock_path = ROOT / "daisy.lock"
    if not manifest.exists():
        print("daisy.toml not found")
        return 1
    manifest_data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    deps = manifest_data.get("dependencies", {})
    if not isinstance(deps, dict):
        print("dependencies must be a table")
        return 1
    if not lock_path.exists():
        print("daisy.lock not found")
        return 1
    lock_data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    lock_deps = lock_data.get("dependencies", {})
    if not isinstance(lock_deps, dict):
        print("daisy.lock missing [dependencies]")
        return 1
    failures = 0
    deps_root = ROOT / "deps"
    deps_on_disk = _discover_deps(deps_root)
    manifest_names = set(deps.keys())
    extra = deps_on_disk - manifest_names
    if extra:
        print(f"unlisted deps in deps/: {sorted(extra)}")
        failures += 1
    missing = manifest_names - deps_on_disk
    if missing:
        print(f"missing deps on disk: {sorted(missing)}")
        failures += 1
    lock_names = set(lock_deps.keys())
    extra_lock = lock_names - manifest_names
    if extra_lock:
        print(f"extra dependencies in daisy.lock: {sorted(extra_lock)}")
        failures += 1
    missing_lock = manifest_names - lock_names
    if missing_lock:
        print(f"dependencies missing in daisy.lock: {sorted(missing_lock)}")
        failures += 1
    for name, spec in deps.items():
        if not isinstance(spec, dict):
            print(f"dependency {name} must be a table")
            failures += 1
            continue
        if "git" in spec or "url" in spec:
            print(f"dependency {name} uses remote source")
            failures += 1
            continue
        path = spec.get("path")
        version = spec.get("version")
        if not isinstance(path, str) or not isinstance(version, str):
            print(f"dependency {name} must define path and version")
            failures += 1
            continue
        if any(version.startswith(prefix) for prefix in ("^", "~", "*")) or any(ch in version for ch in "<>="):
            print(f"dependency {name} version not pinned: {version}")
            failures += 1
            continue
        lock_spec = lock_deps.get(name)
        if not isinstance(lock_spec, dict):
            print(f"dependency {name} missing from daisy.lock")
            failures += 1
            continue
        if lock_spec.get("path") != path or lock_spec.get("version") != version:
            print(f"dependency {name} lock mismatch")
            failures += 1
            continue
        dep_path = ROOT / path
        if dep_path.exists():
            dep_manifest = dep_path / "daisy.toml"
            if dep_manifest.exists():
                dep_data = tomllib.loads(dep_manifest.read_text(encoding="utf-8"))
                dep_version = dep_data.get("package", {}).get("version")
                if dep_version and dep_version != version:
                    print(f"dependency {name} version mismatch: {dep_version} != {version}")
                    failures += 1
        actual_hash = _hash_dir(dep_path)
        expected_hash = lock_spec.get("sha256")
        if actual_hash is None:
            print(f"dependency {name} path missing: {dep_path}")
            failures += 1
            continue
        if expected_hash != actual_hash:
            print(f"dependency {name} hash mismatch")
            failures += 1
            continue
    return failures


def _hash_dir(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted([d for d in dirs if d not in IGNORE_DIRS])
        files_sorted = sorted(files)
        for name in files_sorted:
            ext = Path(name).suffix
            if ext in IGNORE_EXTS:
                continue
            file_path = Path(root) / name
            rel = file_path.relative_to(path).as_posix()
            digest.update(rel.encode("utf-8"))
            digest.update(b"\0")
            try:
                data = file_path.read_bytes()
            except OSError:
                return None
            digest.update(data)
    return digest.hexdigest()


def _discover_deps(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {p.name for p in root.iterdir() if p.is_dir()}


if __name__ == "__main__":
    sys.exit(main())

