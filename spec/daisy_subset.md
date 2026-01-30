# DAISY Subset (Stage 0/1)

This subset is the bootstrap target supported by `/compiler-bootstrap` and
implemented in `/compiler-daisy`.

## Supported Constructs
- `module` / `모듈`
- Function definitions (with generics)
- `let` / `설정한다` (assignment)
- `+=` / `더한다`
- `if` / `만약 ...이면` (+ `else`/`elif` and `아니면`)
- `repeat N` / `N번 반복한다`
- `print` / `출력한다`
- `return` / `반환한다`
- `match/case/else` with enum/struct patterns and guards
- `try` expression for Result/Option propagation
- `struct` and `enum` definitions
- `trait` and `impl` definitions
- Buffer creation and slicing borrow
- Borrowing expressions (`borrow`, `borrow mutable`)
- `move`, `copy` (Copy types only)

## Types
- `int`, `bool`, `string`
- `buffer` (region/arena owning)
- `view` (borrowed slice with lifetime)
- `tensor` (runtime-managed)
- `struct` / `enum` (user-defined, generic)
- `Result` / `Option` stdlib enums

## Ownership Rules
- Move by default.
- Borrow checks are lexical.
- Region cannot be released while borrows are alive.


