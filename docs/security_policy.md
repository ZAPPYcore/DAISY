# Security Policy

This document defines the official security process for DAISY.

## Scope
- Compiler, runtime, standard library, build tools, and CI scripts in this repo.
- Examples and tests are in scope for vulnerability discovery.

## Supported Versions
- The latest main branch is supported.
- Release branches are supported until the next minor release.

## Reporting
- Open a private issue in the tracker or email the maintainers.
- Provide a minimal repro, platform, and compiler/runtime versions.

## Response Targets
- Acknowledge within 48 hours.
- Triage and severity within 7 days.
- Fix and advisory target: 30 days for high/critical, 90 days for medium/low.

## Disclosure
- Coordinated disclosure by default.
- A public advisory is published with mitigation guidance.

## Security Testing Expectations
- `DAISY_SANITIZE=address` in CI.
- `python tests/security/run_security_tests.py` on every CI run.
- `python tools/security/audit.py` as a static runtime boundary check.
- `python tools/security/supply_chain_audit.py` for dependency integrity.
- Long stress tests and fuzzers are mandatory for releases.

