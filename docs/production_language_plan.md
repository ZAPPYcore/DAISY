# Production Language Plan

This plan focuses on hardening DAISY as a production-grade systems language.
It does not include claims of AGI/ASI behavior or guarantees of intelligence.

## Phase 1: Language & Stdlib Hardening
- Complete `Result`/`Option` APIs (map/flatten/expect/unwrap variants) with tests.
- Eliminate remaining stdlib stubs (verify each exported API maps to runtime).
- Add usage examples for all stdlib modules with runnable tests.

## Phase 2: Compiler Correctness & Diagnostics
- Expand fuzzing to parser/typecheck/borrowcheck/irgen.
- Add runtime execution tests for fs/net/concurrency examples.
- Improve diagnostics with actionable hints and precise spans.

## Phase 3: Borrowing & Lifetime Analysis
- CFG-based liveness rules for borrow expiration and move blocking.
- Add dedicated tests for borrow conflicts across branches/loops.
- Document the borrow rules and their rationale.

## Phase 4: Runtime Safety & Observability
- Add sanitizer build flags in CLI (`--sanitize address`).
- Add stress tests that run with sanitizers enabled.
- Expand runtime error model validation tests.

## Phase 5: Tooling & CI
- Stage1 compiler build path (`daisy build-stage1`) in CI.
- Long test suite (`daisy test --long`) in CI.
- Publish reproducible build/ABI checks in CI.

## Phase 6: Packaging & Release Discipline
- ABI change log enforcement + version policy.
- Dependency resolution integration tests.
- Release checklist with backwards compatibility gates.


