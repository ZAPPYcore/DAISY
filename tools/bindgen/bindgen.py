from __future__ import annotations

import subprocess
from pathlib import Path


def run_bindgen(mode: str, target: str) -> int:
    if mode == "rust":
        return _bindgen_rust(Path(target))
    if mode == "export":
        return _bindgen_export(Path(target))
    print("bindgen: supported modes are rust, export")
    return 1


def _bindgen_rust(crate_path: Path) -> int:
    header = crate_path / "include" / "daisy_exports.h"
    if not header.exists():
        print("bindgen: expected header at include/daisy_exports.h (run cbindgen)")
        return 1
    out = crate_path / "daisy_bindings.dsy"
    content = header.read_text(encoding="utf-8")
    stubs = ["module rust_bindings", ""]
    for line in content.splitlines():
        if line.startswith("extern"):
            stubs.append(f"// {line}")
    out.write_text("\n".join(stubs) + "\n", encoding="utf-8")
    print(f"bindgen: wrote {out}")
    return 0


def _bindgen_export(target: Path) -> int:
    rs_path = target / "daisy_export.rs"
    rs_path.write_text(
        "\n".join(
            [
                "//! Auto-generated DAISY export wrapper",
                "use std::ffi::c_void;",
                "",
                "#[link(name = \"daisy_module\")]",
                "extern \"C\" {",
                "  pub fn daisy_main() -> i64;",
                "}",
                "",
                "pub fn call_daisy_main() -> i64 {",
                "  unsafe { daisy_main() }",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"bindgen: wrote {rs_path}")
    return 0


