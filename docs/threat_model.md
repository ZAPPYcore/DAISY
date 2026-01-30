# Threat Model

## Assets
- Runtime memory safety and object lifetimes.
- File system and network boundaries.
- Compiler correctness and artifact integrity.

## Trust Boundaries
- External inputs: files, sockets, environment variables.
- FFI calls into runtime and platform APIs.
- Build artifacts across dependency graph.

## Attacker Model
- Controls program input and network peers.
- Attempts to trigger out-of-bounds reads, leaks, or hangs.
- Attempts to induce resource exhaustion or data corruption.

## Key Risks
- Memory safety: buffer/view misuse, use-after-free, leaks.
- Concurrency: data races, deadlocks, channel misuse.
- DoS: unbounded reads, large allocations, pathological inputs.
- Supply chain: dependency ABI mismatch or tampering.

## Mitigations
- Runtime checks (`DAISY_RT_CHECKS`) and sanitizer coverage.
- Hard limits for external reads (`DAISY_MAX_FILE_SIZE`, `DAISY_MAX_NET_READ`).
- Memory tracking counters for live allocations.
- ABI validation and build cache integrity checks.
- Security test suite enforcing failure on boundary violations.

## Open Items
- Expanded fuzzing for runtime input parsers.
- Formal verification of borrow and IR transformations.

