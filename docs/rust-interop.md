# Rust <-> DAISY Interop

DAISY uses a C ABI boundary for interoperability. Rust ABI is unstable.

## DAISY Depending on Rust Crates
1. Create a Rust crate that exports `extern "C"` functions.
2. Build as `staticlib` or `cdylib`.
3. Declare externs in DAISY:
   - `extern fn rust_add(a:int, b:int) -> int`
4. Link the Rust library in the build step (see `/examples/rust_crate`).

## Rust Depending on DAISY
1. Build DAISY to a staticlib or cdylib.
2. Use `daisy bindgen export` to generate a Rust wrapper.
3. Link and call the exported DAISY functions in Rust.

## Cargo Bridge
- `daisy pkg add <crate>` writes `daisy.toml` and `daisy.lock`.
- Lockfile stores integrity hashes for reproducible builds.
- Vendor mode can be implemented by copying Cargo registry sources to `/vendor`.

## Security
- Use `cargo-audit` with the same dependency graph.
- Require explicit policy to enable build scripts.


