# CI Plan

Required CI jobs:
- Build and run examples on Linux and Windows.
- Run `python tools/cli/daisy.py test`.
- Run `python tools/security/audit.py`.
- Run `python tools/security/supply_chain_audit.py`.
- Run `python ci/run_ci.py`.
- Run `python tests/fuzz_lexer.py`.
- Run `python tests/fuzz_compile.py`.
- Run `python tests/fuzz_irgen.py`.
- Run `python tests/security/run_security_tests.py`.
- Run `python tools/cli/daisy.py build-stage1`.
- Build Rust interop examples:
  - `/examples/rust_crate`
  - `/examples/rust_calls_daisy`

Suggested commands:
- `python ci/run_ci.py`
- `python tools/cli/daisy.py build examples/english_hello.dsy`
- `python tools/cli/daisy.py build examples/korean_hello.dsy`
- `python tools/cli/daisy.py build examples/tensor_matmul.dsy`
- `python tools/cli/daisy.py build examples/concurrency.dsy`
- `python tools/cli/daisy.py test`
- `python tools/security/audit.py`
- `python tools/security/supply_chain_audit.py`
- `python tests/fuzz_lexer.py`
- `python tests/fuzz_compile.py`
- `python tests/fuzz_irgen.py`
- `python tests/security/run_security_tests.py`
- `python tools/cli/daisy.py test --long`
- `python tools/cli/daisy.py build-stage1`
- `cargo build --manifest-path examples/rust_crate/Cargo.toml`
- `cargo build --manifest-path examples/rust_calls_daisy/Cargo.toml`


