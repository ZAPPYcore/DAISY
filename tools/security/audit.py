from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    rt_c = ROOT / "runtime" / "rt.c"
    if not rt_c.exists():
        print("runtime/rt.c not found")
        return 1
    lines = rt_c.read_text(encoding="utf-8").splitlines()
    checks = {
        "daisy_file_read": ["DAISY_MAX_FILE_SIZE", "daisy_checked_add_size", "size < 0"],
        "daisy_net_recv": ["DAISY_MAX_NET_READ", "DAISY_RT_ASSERT", "sock"],
        "daisy_net_send": ["DAISY_RT_ASSERT", "sock"],
        "daisy_str_concat": ["daisy_checked_add_size"],
    }
    failures = 0
    for func, tokens in checks.items():
        body = _extract_function_body(lines, func)
        if body is None:
            print(f"audit failed: function missing {func}")
            failures += 1
            continue
        missing = [token for token in tokens if token not in body]
        if missing:
            print(f"audit failed: {func} missing {missing}")
            failures += 1
    return failures


def _extract_function_body(lines: list[str], func_name: str) -> str | None:
    start_idx = None
    for idx, line in enumerate(lines):
        if func_name in line and "(" in line and "{" in line:
            start_idx = idx
            break
    if start_idx is None:
        return None
    brace_count = 0
    collected: list[str] = []
    for line in lines[start_idx:]:
        if "{" in line:
            brace_count += line.count("{")
        if "}" in line:
            brace_count -= line.count("}")
        collected.append(line)
        if brace_count == 0 and collected:
            break
    return "\n".join(collected)


if __name__ == "__main__":
    raise SystemExit(main())

