# DAISY Locked Decisions (v0/v1)

This document captures locked architectural decisions for DAISY.

## Backend
- AOT C backend only (portable C11).
- Build via clang/gcc.
- Optional LTO flag supported by the build driver.

## IR
- Typed SSA-like IR.
- Tensor intrinsics and fusion hooks are first-class IR ops.

## Safety
- Safe-by-default.
- `unsafe:` blocks are required for unsafe operations.
- Unsafe blocks must include explicit justification comments.
 - Unsafe blocks may bypass release-with-live-borrow checks only.
 - Borrow alias conflicts remain errors even inside unsafe.
 - Use-after-move remains a hard error even inside unsafe.
 - Unsafe usage is logged to `build/<module>.unsafe.log`.
 - Runtime checks can be enabled with `daisy build --rt-checks`.

## Diagnostics
- Borrow checker reports move origin and conflicting borrow variable names.

## Self-Hosting Path
- Stage 0: `/compiler-bootstrap` builds a DAISY subset into C.
- Stage 1: `/compiler-daisy` implements subset compiler in DAISY.
- Stage 2: compile `/compiler-daisy` using stage 0 output.
- Stage 3: self-compile and remove bootstrap dependency.

## Language Surface
- English-prose and Korean-prose are equal, first-class surface syntaxes.
- Both surfaces map to the same unified AST.
- `match/case/else` are supported in the English surface for control flow.
- `match` supports enum/struct patterns with optional guards.
- `struct` and `enum` are supported in the English surface.
- `if/elif/else` control flow and short-circuit logical operators (`and/or`) are supported.
- `try` expression propagates `Result` / `Option` early returns.
- Generic type parameters support trait bounds (`<T: Trait + ...>`).

## Dependencies
- `daisy.toml` `[dependencies]` supports local path deps.
- Version requirements support exact `x.y.z` and caret `^x.y.z` (same major, >= base).
- Dependency ABI major must match current compiler ABI major when abi manifests exist.

## Workspace
- `daisy.toml` `[workspace]` supports `members = ["path"]` for multi-package repos.
- Workspace members support glob patterns like `libs/*`.
- Workspace members are added to module search paths for import resolution.

## Build Cache
- Per-module build cache keyed by source hash + ABI version.
- Cached modules skip C regeneration when unchanged.

## Benchmarking
- `bench/bench.py` runs the C vs DAISY benchmark suite.
- Benchmarks compile with `-O2` and report min of 3 runs after 1 warmup.
- `daisy bench --json` writes structured results to `bench/results.json`.

## Tooling
- `daisy lsp` runs the built-in LSP server.
- `daisy test --long` runs long-duration stability tests.
- `daisy build --emit-ir` writes per-module IR dumps to `build/*.ir.txt`.
- `daisy build --profile` writes `build/profile.json` with compiler phase timings.

## Error Model
- Runtime exposes thread-local last error string via `errors.last()`.
- File I/O errors include OS error messages when available.

## Borrowing / Ownership
- Rust-grade ownership & borrowing.
- Move semantics by default.
- Borrowing: immutable `&` and mutable `&mut`.
- Lexical lifetimes for v0; plan for NLL in v1+.
- Alias rule: either one mutable borrow OR many immutable borrows.


