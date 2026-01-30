# Korean Surface Syntax Mapping Table

This file defines the required Korean surface patterns and their mapping
to AST operations. English and Korean surfaces are parsed into the same AST.

## Patterns (Required)

| Korean Pattern | AST Operation | Notes |
| --- | --- | --- |
| `모듈 NAME` | `Module(name=NAME)` | Module declaration |
| `함수를 정의한다 NAME은 ARGS를 받고 TYPE을 반환한다:` | `FunctionDef` | Korean prose form |
| `공개 함수를 정의한다 ...` | `FunctionDef(is_public=True)` | Public function |
| `비공개 함수를 정의한다 ...` | `FunctionDef(is_public=False)` | Private function |
| `함수 NAME 정의:` | `FunctionDef` | Short form |
| `모듈을 NAME` | `Import(module=NAME)` | Import module |
| `모듈을 NAME 별칭으로 ALIAS` | `Import(alias=ALIAS)` | Import with alias |
| `사용 NAME` / `사용한다 NAME` | `Import(is_use=True)` | Use-import for unqualified calls |
| `X를 Y로 설정한다` | `Assign(target=X, value=Y)` | Assign |
| `X에 Y를 더한다` | `AddAssign(target=X, value=Y)` | Add-assign |
| `만약 조건이면:` | `If(condition=조건)` | If |
| `조건이면:` | `If(condition=조건)` | If short |
| `아니면:` | `else` | Else block |
| `아니면 조건이면:` | `elif` | Else-if |
| `N번 반복한다:` | `Repeat(count=N)` | Repeat |
| `반복한다:` | `Repeat(count=? )` | Repeat with explicit loop var |
| `"TEXT"를 출력한다` | `Print(value=TEXT)` | Print |
| `반환한다` | `Return(value=none)` | Return |
| `X을 반환한다` / `X를 반환한다` | `Return(value=X)` | Return value |
| `버퍼를 N바이트로 생성한다` | `BufferCreate(size=N)` | Region/arena |
| `뷰를 버퍼의 A부터 B까지로 빌려온다(불변)` | `Borrow(kind=immut)` | Borrow view |
| `뷰를 버퍼의 A부터 B까지로 빌려온다(가변)` | `Borrow(kind=mut)` | Borrow view |
| `소유권을 이동한다 X -> Y` | `Move(src=X, dst(alpha))` | Move |
| `X를 해제한다` | `Release(target=X)` | Release (borrow-checked) |
| `빌려온다(불변) X` | `BorrowExpr(kind=immut, value=X)` | Borrow expr |
| `빌려온다(가변) X` | `BorrowExpr(kind=mut, value=X)` | Borrow expr |
| `복사한다 X` | `CopyExpr(value=X)` | Copy types only |
| `X 그리고 Y` | `LogicalOp(and)` | Short-circuit AND |
| `X 또는 Y` | `LogicalOp(or)` | Short-circuit OR |
| `케이스 P 만약 G이면:` | `MatchCase(guard=G)` | Match guard |
| `케이스 구조체(패턴...)` | `StructPattern` | Struct destructuring |
| `케이스 이름` | `BindPattern` | Bind match value |
| `시도 EXPR` | `TryExpr` | Result/Option propagation |
| `시도한다 EXPR` | `TryExpr` | Result/Option propagation |
| `함수<T: 트레잇>` | `TypeParam(bounds)` | Generic constraints |

## Disambiguation Strategy

Priority rules (first match wins):
1. Block-introducing patterns with `:` (e.g., `만약 ...이면:`).
2. Explicit keyword patterns (`반환한다`, `출력한다`, `설정한다`).
3. General expression parsing.

Escape hatch:
- Prefix a line with `영어:` or `한국어:` to force the parser to use the
  specific surface grammar for that line.

## Fixed Pattern List
- See `spec/korean_patterns.md` for the fixed 200 Korean patterns.

## Unsafe Blocks
- `unsafe "reason":` or `위험 "reason":` introduces an unsafe block.
- Unsafe blocks require a justification string.
## Spacing & Indentation
- Indentation is 2 spaces per block level.
- One space between tokens except within quoted strings.
- Particles (`을/를/에/의/부터/까지/로/으로`) are tokenized as grammatical markers.


