from __future__ import annotations

from typing import List, Optional, Tuple

from compiler_core import ast
from compiler_core.diagnostics import Span
from compiler_bootstrap.lexer import Token, tokenize


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: List[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def parse_module(self) -> ast.Module:
        self._skip_newlines()
        keyword = self._expect_ident()
        if keyword.value not in ("module", "모듈"):
            raise self._error(keyword, "First line must declare module")
        name = self._expect_ident()
        self._expect("NEWLINE")
        body = self._parse_block()
        return ast.Module(name=name.value, body=body, span=self._span([keyword, name]))

    def _parse_block(self) -> List[ast.Stmt]:
        stmts: List[ast.Stmt] = []
        while not self._peek("EOF") and not self._peek("DEDENT"):
            if self._peek("NEWLINE"):
                self._advance()
                continue
            stmts.append(self._parse_stmt())
        if self._peek("DEDENT"):
            self._advance()
        return stmts

    def _parse_stmt(self) -> ast.Stmt:
        tok = self._peek_token()
        if tok.value in ("export", "public", "공개"):
            self._advance()
            next_tok = self._peek_token()
            if next_tok.value in ("extern", "외부"):
                return self._parse_extern(is_public=True)
            if next_tok.value in ("trait", "트레잇"):
                return self._parse_trait(is_public=True)
            if next_tok.value in ("struct", "구조체"):
                return self._parse_struct(is_public=True)
            if next_tok.value in ("enum", "열거형"):
                return self._parse_enum(is_public=True)
            if next_tok.value in ("fn", "함수", "함수를"):
                return self._parse_function(is_public=True)
            raise self._error(next_tok, "export must be followed by function or extern")
        if tok.value in ("private", "비공개"):
            self._advance()
            next_tok = self._peek_token()
            if next_tok.value in ("extern", "외부"):
                return self._parse_extern(is_public=False)
            if next_tok.value in ("trait", "트레잇"):
                return self._parse_trait(is_public=False)
            if next_tok.value in ("struct", "구조체"):
                return self._parse_struct(is_public=False)
            if next_tok.value in ("enum", "열거형"):
                return self._parse_enum(is_public=False)
            if next_tok.value in ("fn", "함수", "함수를"):
                return self._parse_function(is_public=False)
            raise self._error(next_tok, "private must be followed by function or extern")
        if tok.value in ("import", "use", "사용", "사용한다", "모듈을", "모듈"):
            return self._parse_import()
        if tok.value in ("extern", "외부"):
            return self._parse_extern()
        if tok.value in ("trait", "트레잇"):
            return self._parse_trait(is_public=False)
        if tok.value in ("impl", "구현"):
            return self._parse_impl()
        if tok.value in ("struct", "구조체"):
            return self._parse_struct(is_public=False)
        if tok.value in ("enum", "열거형"):
            return self._parse_enum(is_public=False)
        if tok.value in ("fn", "함수", "함수를"):
            return self._parse_function()
        if tok.value in ("while", "동안"):
            return self._parse_while()
        if tok.value in ("continue", "계속한다"):
            self._advance()
            self._expect("NEWLINE")
            return ast.Continue(span=self._span([tok]))
        if tok.value in ("break", "중단한다"):
            self._advance()
            self._expect("NEWLINE")
            return ast.Break(span=self._span([tok]))
        if tok.value in ("unsafe", "위험"):
            return self._parse_unsafe()
        if tok.value in ("if", "만약") or self._line_ends_with("이면"):
            return self._parse_if()
        if tok.value in ("match", "맞춤"):
            return self._parse_match()
        if tok.value in ("repeat",) or self._line_contains(("번", "반복한다")):
            return self._parse_repeat()
        if tok.value in ("unsafe", "위험"):
            return self._parse_unsafe()
        if tok.value in ("set",) or self._line_contains(("설정한다",)):
            return self._parse_assign()
        if (tok.value in ("add",) and self._line_contains(("to",))) or self._line_contains(("더한다",)):
            return self._parse_add_assign()
        if tok.value in ("print",) or self._line_contains(("출력한다",)):
            return self._parse_print()
        if tok.value in ("return",) or self._line_contains(("반환한다",)):
            return self._parse_return()
        if self._line_contains(("생성한다", "바이트")):
            return self._parse_buffer_create()
        if self._line_contains(("빌려온다", "부터", "까지")):
            return self._parse_borrow_slice()
        if self._line_contains(("이동한다",)):
            return self._parse_move()
        if self._line_contains(("해제한다",)) or tok.value == "release":
            return self._parse_release()
        raise self._error(tok, "Unrecognized statement")

    def _parse_extern(self, is_public: bool = False) -> ast.ExternFunctionDef:
        start = self._peek_token()
        if start.value == "extern":
            self._advance()
            self._expect_value("fn")
        else:
            self._advance()
            self._expect_value("함수")
        name = self._expect_ident()
        params = self._parse_params()
        self._expect_value("->")
        return_type = self._parse_type_ref()
        self._expect("NEWLINE")
        return ast.ExternFunctionDef(
            name=name.value,
            params=params,
            return_type=return_type,
            is_public=is_public,
        )

    def _parse_struct(self, is_public: bool = False) -> ast.StructDef:
        start = self._peek_token()
        self._advance()
        name = self._expect_ident()
        type_params = self._parse_type_params()
        self._expect("PUNCT", ":")
        self._expect("NEWLINE")
        self._expect("INDENT")
        fields: List[ast.StructField] = []
        while not self._peek("DEDENT") and not self._peek("EOF"):
            if self._peek("NEWLINE"):
                self._advance()
                continue
            field_name = self._expect_ident()
            self._expect("PUNCT", ":")
            field_type = self._parse_type_ref()
            self._expect("NEWLINE")
            fields.append(ast.StructField(name=field_name.value, type_ref=field_type))
        if self._peek("DEDENT"):
            self._advance()
        return ast.StructDef(
            name=name.value,
            type_params=type_params,
            fields=fields,
            is_public=is_public,
            span=self._span([start, name]),
        )

    def _parse_enum(self, is_public: bool = False) -> ast.EnumDef:
        start = self._peek_token()
        self._advance()
        name = self._expect_ident()
        type_params = self._parse_type_params()
        self._expect("PUNCT", ":")
        self._expect("NEWLINE")
        self._expect("INDENT")
        cases: List[ast.EnumCase] = []
        while not self._peek("DEDENT") and not self._peek("EOF"):
            if self._peek("NEWLINE"):
                self._advance()
                continue
            tok = self._peek_token()
            if tok.value not in ("case", "케이스"):
                raise self._error(tok, "Expected case in enum")
            self._advance()
            case_name = self._expect_ident()
            payload = None
            if self._peek("PUNCT", ":"):
                self._advance()
                payload = self._parse_type_ref()
            self._expect("NEWLINE")
            cases.append(ast.EnumCase(name=case_name.value, payload=payload, span=self._span([tok, case_name])))
        if self._peek("DEDENT"):
            self._advance()
        return ast.EnumDef(
            name=name.value,
            type_params=type_params,
            cases=cases,
            is_public=is_public,
            span=self._span([start, name]),
        )

    def _parse_trait(self, is_public: bool = False) -> ast.TraitDef:
        start = self._peek_token()
        self._advance()
        name = self._expect_ident()
        type_params = self._parse_type_params()
        self._expect("PUNCT", ":")
        self._expect("NEWLINE")
        self._expect("INDENT")
        methods: List[ast.TraitMethod] = []
        while not self._peek("DEDENT") and not self._peek("EOF"):
            if self._peek("NEWLINE"):
                self._advance()
                continue
            tokens = self._consume_line()
            method = self._parse_trait_method(tokens)
            methods.append(method)
            self._expect("NEWLINE")
        if self._peek("DEDENT"):
            self._advance()
        return ast.TraitDef(
            name=name.value,
            type_params=type_params,
            methods=methods,
            is_public=is_public,
            span=self._span([start, name]),
        )

    def _parse_impl(self) -> ast.ImplDef:
        start = self._peek_token()
        tokens = self._consume_line()
        if tokens[-1].value == ":":
            tokens = tokens[:-1]
        trait_name: Optional[str] = None
        for_type_tokens: List[Token] = []
        if "for" in [t.value for t in tokens]:
            idx_for = next(i for i, t in enumerate(tokens) if t.value == "for")
            if idx_for >= 2:
                trait_name = tokens[1].value
            for_type_tokens = tokens[idx_for + 1 :]
        else:
            for_type_tokens = tokens[1:]
        if not for_type_tokens:
            raise self._error(start, "impl requires target type")
        for_type = self._parse_type_ref_tokens(for_type_tokens, 0)[0]
        self._expect("NEWLINE")
        self._expect("INDENT")
        methods: List[ast.FunctionDef] = []
        while not self._peek("DEDENT") and not self._peek("EOF"):
            if self._peek("NEWLINE"):
                self._advance()
                continue
            method = self._parse_function()
            methods.append(method)
        if self._peek("DEDENT"):
            self._advance()
        return ast.ImplDef(trait_name=trait_name, for_type=for_type, methods=methods, span=self._span([start]))

    def _parse_import(self) -> ast.Import:
        start = self._peek_token()
        is_use = start.value in ("use", "사용", "사용한다")
        self._advance()
        if start.value == "모듈" and self._peek("PART") and self._peek_token().value in ("을", "를"):
            self._advance()
        alias = None
        if self._peek("STRING"):
            mod = self._advance()
            if self._peek_value("as") or self._peek_value("별칭"):
                self._advance()
                if self._peek("PART") and self._peek_token().value in ("로", "으로"):
                    self._advance()
                alias = self._expect_ident()
            self._expect("NEWLINE")
            return ast.Import(
                module=mod.value,
                alias=alias.value if alias else None,
                is_use=is_use,
                span=self._span([start, mod] + ([alias] if alias else [])),
            )
        name = self._expect_ident()
        if self._peek_value("as") or self._peek_value("별칭"):
            self._advance()
            if self._peek("PART") and self._peek_token().value in ("로", "으로"):
                self._advance()
            alias = self._expect_ident()
        self._expect("NEWLINE")
        return ast.Import(
            module=name.value,
            alias=alias.value if alias else None,
            is_use=is_use,
            span=self._span([start, name] + ([alias] if alias else [])),
        )

    def _parse_function(self, is_public: bool = False) -> ast.FunctionDef:
        start = self._peek_token()
        if start.value == "fn":
            self._advance()
            name = self._expect_ident()
            type_params = self._parse_type_params()
            params = self._parse_params()
            self._expect_value("->")
            return_type = self._parse_type_ref()
            self._expect("PUNCT", ":")
            self._expect("NEWLINE")
            self._expect("INDENT")
            body = self._parse_block()
            return ast.FunctionDef(
                name=name.value,
                type_params=type_params,
                params=params,
                return_type=return_type,
                body=body,
                is_public=is_public,
                span=self._span([start, name]),
            )
        tokens = self._consume_line()
        name_token, params, return_type = self._parse_korean_function_header(tokens)
        self._expect("NEWLINE")
        self._expect("INDENT")
        body = self._parse_block()
        return ast.FunctionDef(
            name=name_token.value,
            type_params=[],
            params=params,
            return_type=ast.TypeRef(return_type.value),
            body=body,
            is_public=is_public,
            span=self._span(tokens),
        )

    def _parse_if(self) -> ast.If:
        if self._peek_value("if"):
            start_tok = self._advance()
            cond = self._parse_expr_until(":")
            self._expect("PUNCT", ":")
            cond_tokens = [start_tok]
        else:
            tokens = self._consume_line()
            cond_tokens = tokens[1:] if tokens and tokens[0].value == "만약" else tokens[:-1]
            cond = self._parse_condition(cond_tokens)
        self._expect("NEWLINE")
        self._expect("INDENT")
        body = self._parse_block()
        else_body = self._parse_if_tail()
        return ast.If(
            condition=cond,
            body=body,
            else_body=else_body,
            span=self._span_from_tokens(cond_tokens if "cond_tokens" in locals() else []),
        )

    def _parse_if_tail(self) -> Optional[List[ast.Stmt]]:
        if self._peek_value("elif"):
            self._advance()
            cond = self._parse_expr_until(":")
            self._expect("PUNCT", ":")
            self._expect("NEWLINE")
            self._expect("INDENT")
            body = self._parse_block()
            tail = self._parse_if_tail()
            return [ast.If(condition=cond, body=body, else_body=tail)]
        if self._peek_value("else"):
            self._advance()
            self._expect("PUNCT", ":")
            self._expect("NEWLINE")
            self._expect("INDENT")
            return self._parse_block()
        if self._peek_value("아니면"):
            tokens = self._consume_line()
            if len(tokens) == 2 and tokens[1].value == ":":
                self._expect("NEWLINE")
                self._expect("INDENT")
                return self._parse_block()
            cond_tokens = tokens[1:] if tokens and tokens[0].value == "아니면" else tokens[:-1]
            cond = self._parse_condition(cond_tokens)
            self._expect("NEWLINE")
            self._expect("INDENT")
            body = self._parse_block()
            tail = self._parse_if_tail()
            return [ast.If(condition=cond, body=body, else_body=tail)]
        return None

    def _parse_match(self) -> ast.Match:
        start = self._peek_token()
        self._advance()
        value = self._parse_expr_until(":")
        self._expect("PUNCT", ":")
        self._expect("NEWLINE")
        self._expect("INDENT")
        cases: List[ast.MatchCase] = []
        else_body: Optional[List[ast.Stmt]] = None
        while not self._peek("DEDENT") and not self._peek("EOF"):
            if self._peek("NEWLINE"):
                self._advance()
                continue
            tok = self._peek_token()
            if tok.value in ("case", "케이스"):
                tokens = self._consume_line()
                if not tokens or tokens[0].value not in ("case", "케이스"):
                    raise self._error(tok, "Expected case line")
                if tokens[-1].value == ":":
                    tokens = tokens[:-1]
                guard_idx = next(
                    (idx for idx, t in enumerate(tokens) if t.value in ("if", "만약")),
                    None,
                )
                if guard_idx is not None:
                    pattern_tokens = tokens[1:guard_idx]
                    guard_tokens = tokens[guard_idx + 1 :]
                    guard = self._parse_condition(guard_tokens) if tokens[guard_idx].value == "만약" else self._parse_expr_tokens(guard_tokens)
                else:
                    pattern_tokens = tokens[1:]
                    guard = None
                case_pattern = self._parse_pattern_tokens(pattern_tokens)
                self._expect("NEWLINE")
                self._expect("INDENT")
                body = self._parse_block()
                cases.append(ast.MatchCase(pattern=case_pattern, body=body, guard=guard, span=self._span([tok])))
                continue
            if tok.value in ("else", "아니면"):
                self._advance()
                self._expect("PUNCT", ":")
                self._expect("NEWLINE")
                self._expect("INDENT")
                else_body = self._parse_block()
                continue
            raise self._error(tok, "Expected case or else in match")
        if self._peek("DEDENT"):
            self._advance()
        return ast.Match(value=value, cases=cases, else_body=else_body, span=self._span([start]))

    def _parse_repeat(self) -> ast.Repeat:
        if self._peek_value("repeat"):
            self._advance()
            count = self._parse_expr_until(":")
            self._expect("PUNCT", ":")
        else:
            tokens = self._consume_line()
            count = self._parse_expr_tokens(tokens[:-3])
        self._expect("NEWLINE")
        self._expect("INDENT")
        body = self._parse_block()
        return ast.Repeat(count=count, body=body, span=self._span_from_tokens(tokens if "tokens" in locals() else []))

    def _parse_unsafe(self) -> ast.UnsafeBlock:
        start = self._peek_token()
        self._advance()
        reason = None
        if self._peek("STRING"):
            reason_tok = self._advance()
            reason = reason_tok.value
        self._expect("PUNCT", ":")
        self._expect("NEWLINE")
        self._expect("INDENT")
        body = self._parse_block()
        return ast.UnsafeBlock(reason=reason, body=body, span=self._span([start]))

    def _parse_while(self) -> ast.While:
        if self._peek_value("while"):
            start = self._advance()
            cond = self._parse_expr_until(":")
            self._expect("PUNCT", ":")
            self._expect("NEWLINE")
            self._expect("INDENT")
            body = self._parse_block()
            return ast.While(condition=cond, body=body, span=self._span([start]))
        tokens = self._consume_line()
        cond = self._parse_expr_tokens(tokens[1:-1])
        self._expect("NEWLINE")
        self._expect("INDENT")
        body = self._parse_block()
        return ast.While(condition=cond, body=body, span=self._span(tokens))

    def _parse_assign(self) -> ast.Assign:
        if self._peek_value("set"):
            self._advance()
            target = self._parse_expr_until("=")
            self._expect_value("=")
            value = self._parse_expr_until("NEWLINE")
            self._expect("NEWLINE")
            return ast.Assign(target=target, value=value, span=target.span)
        tokens = self._consume_line()
        target = self._parse_expr_tokens(tokens[:1])
        value = self._parse_expr_tokens(tokens[2:-2])
        self._expect("NEWLINE")
        return ast.Assign(target=target, value=value, span=self._span(tokens))

    def _parse_add_assign(self) -> ast.AddAssign:
        if self._peek_value("add"):
            self._advance()
            value = self._parse_expr_until("to")
            self._expect_value("to")
            target = self._parse_expr_until("NEWLINE")
            self._expect("NEWLINE")
            return ast.AddAssign(target=target, value=value, span=target.span)
        tokens = self._consume_line()
        target = self._parse_expr_tokens(tokens[:1])
        value = self._parse_expr_tokens(tokens[2:-2])
        self._expect("NEWLINE")
        return ast.AddAssign(target=target, value=value, span=self._span(tokens))

    def _parse_print(self) -> ast.Print:
        if self._peek_value("print"):
            self._advance()
            value = self._parse_expr_until("NEWLINE")
            self._expect("NEWLINE")
            return ast.Print(value=value, span=value.span)
        tokens = self._consume_line()
        value = self._parse_expr_tokens(tokens[:-2])
        self._expect("NEWLINE")
        return ast.Print(value=value, span=self._span(tokens))

    def _parse_return(self) -> ast.Return:
        if self._peek_value("return"):
            self._advance()
            if self._peek("NEWLINE"):
                self._advance()
                return ast.Return(value=None, span=None)
            value = self._parse_expr_until("NEWLINE")
            self._expect("NEWLINE")
            return ast.Return(value=value, span=value.span)
        tokens = self._consume_line()
        if len(tokens) == 1:
            self._expect("NEWLINE")
            return ast.Return(value=None, span=self._span(tokens))
        value = self._parse_expr_tokens(tokens[:-2])
        self._expect("NEWLINE")
        return ast.Return(value=value, span=self._span(tokens))

    def _parse_buffer_create(self) -> ast.BufferCreate:
        tokens = self._consume_line()
        name = tokens[0]
        size = self._parse_expr_tokens(tokens[2:3])
        self._expect("NEWLINE")
        return ast.BufferCreate(name=name.value, size=size, span=self._span(tokens))

    def _parse_borrow_slice(self) -> ast.BorrowSlice:
        tokens = self._consume_line()
        name = tokens[0].value
        buffer_expr = self._parse_expr_tokens(tokens[2:3])
        start = self._parse_expr_tokens(tokens[4:5])
        end = self._parse_expr_tokens(tokens[6:7])
        mutable = tokens[-2].value == "가변"
        self._expect("NEWLINE")
        return ast.BorrowSlice(name=name, buffer=buffer_expr, start=start, end=end, mutable=mutable, span=self._span(tokens))

    def _parse_move(self) -> ast.Move:
        tokens = self._consume_line()
        src = self._parse_expr_tokens(tokens[2:3])
        dst = tokens[4].value
        self._expect("NEWLINE")
        return ast.Move(src=src, dst=dst, span=self._span(tokens))

    def _parse_release(self) -> ast.Release:
        if self._peek_value("release"):
            self._advance()
            target = self._parse_expr_until("NEWLINE")
            self._expect("NEWLINE")
            return ast.Release(target=target, span=target.span)
        tokens = self._consume_line()
        target = self._parse_expr_tokens(tokens[:1])
        self._expect("NEWLINE")
        return ast.Release(target=target, span=self._span(tokens))

    def _parse_params(self) -> List[ast.Param]:
        self._expect("PUNCT", "(")
        params: List[ast.Param] = []
        if self._peek("PUNCT", ")"):
            self._advance()
            return params
        while True:
            name = self._expect_ident()
            self._expect("PUNCT", ":")
            type_ref = self._parse_type_ref()
            params.append(ast.Param(name=name.value, type_ref=type_ref))
            if self._peek("PUNCT", ","):
                self._advance()
                continue
            break
        self._expect("PUNCT", ")")
        return params

    def _parse_type_params(self) -> List[ast.TypeParam]:
        params: List[ast.TypeParam] = []
        if self._peek("OP", "<"):
            self._advance()
            while True:
                ident = self._expect_ident()
                bounds: List[str] = []
                if self._peek("PUNCT", ":"):
                    self._advance()
                    while True:
                        bound = self._expect_ident()
                        bounds.append(bound.value)
                        if self._peek("OP", "+"):
                            self._advance()
                            continue
                        break
                params.append(ast.TypeParam(name=ident.value, bounds=bounds, span=self._span([ident])))
                if self._peek("PUNCT", ","):
                    self._advance()
                    continue
                if self._peek("OP", ">"):
                    self._advance()
                    break
                raise self._error(self._peek_token(), "Expected ',' or '>' in type params")
        return params

    def _parse_type_ref(self) -> ast.TypeRef:
        name = self._expect_ident()
        args: List[ast.TypeRef] = []
        if self._peek("OP", "<"):
            self._advance()
            while True:
                args.append(self._parse_type_ref())
                if self._peek("PUNCT", ","):
                    self._advance()
                    continue
                if self._peek("OP", ">"):
                    self._advance()
                    break
                raise self._error(self._peek_token(), "Expected ',' or '>' in type args")
        return ast.TypeRef(name=name.value, args=args, span=self._span([name]))

    def _parse_type_ref_tokens(self, tokens: List[Token], idx: int) -> tuple[ast.TypeRef, int]:
        if idx >= len(tokens) or tokens[idx].kind != "IDENT":
            raise self._error(tokens[idx] if idx < len(tokens) else tokens[-1], "Expected type name")
        name_tok = tokens[idx]
        idx += 1
        args: List[ast.TypeRef] = []
        if idx < len(tokens) and tokens[idx].value == "<":
            idx += 1
            while True:
                arg, idx = self._parse_type_ref_tokens(tokens, idx)
                args.append(arg)
                if idx < len(tokens) and tokens[idx].value == ",":
                    idx += 1
                    continue
                if idx < len(tokens) and tokens[idx].value == ">":
                    idx += 1
                    break
                raise self._error(tokens[idx] if idx < len(tokens) else tokens[-1], "Expected ',' or '>' in type args")
        return ast.TypeRef(name=name_tok.value, args=args, span=self._span([name_tok])), idx

    def _parse_trait_method(self, tokens: List[Token]) -> ast.TraitMethod:
        if not tokens:
            raise self._error(self._peek_token(), "Empty trait method")
        if tokens[0].value not in ("fn", "함수"):
            raise self._error(tokens[0], "Trait method must start with fn")
        idx = 1
        if idx >= len(tokens):
            raise self._error(tokens[0], "Trait method missing name")
        name_tok = tokens[idx]
        idx += 1
        if idx >= len(tokens) or tokens[idx].value != "(":
            raise self._error(tokens[idx - 1], "Trait method missing parameters")
        idx += 1
        params: List[ast.Param] = []
        if idx < len(tokens) and tokens[idx].value == ")":
            idx += 1
        else:
            while idx < len(tokens):
                param_name = tokens[idx]
                idx += 1
                if idx >= len(tokens) or tokens[idx].value != ":":
                    raise self._error(param_name, "Trait param missing ':'")
                idx += 1
                param_type, idx = self._parse_type_ref_tokens(tokens, idx)
                params.append(ast.Param(name=param_name.value, type_ref=param_type))
                if idx < len(tokens) and tokens[idx].value == ",":
                    idx += 1
                    continue
                if idx < len(tokens) and tokens[idx].value == ")":
                    idx += 1
                    break
                raise self._error(tokens[idx] if idx < len(tokens) else param_name, "Expected ',' or ')' in params")
        if idx >= len(tokens) or tokens[idx].value != "->":
            raise self._error(tokens[idx - 1], "Trait method missing return type")
        idx += 1
        return_type, idx = self._parse_type_ref_tokens(tokens, idx)
        return ast.TraitMethod(
            name=name_tok.value,
            params=params,
            return_type=return_type,
            span=self._span_from_tokens(tokens),
        )

    def _parse_pattern_until(self, stop: str) -> ast.Pattern:
        tokens: List[Token] = []
        while not self._peek_value(stop) and not self._peek(stop):
            tokens.append(self._advance())
        return self._parse_pattern_tokens(tokens)

    def _parse_pattern_tokens(self, tokens: List[Token]) -> ast.Pattern:
        if not tokens:
            return ast.WildcardPattern()
        if len(tokens) == 1 and tokens[0].value == "_":
            return ast.WildcardPattern(span=self._span(tokens))
        if len(tokens) == 1 and tokens[0].kind == "IDENT" and tokens[0].value not in ("true", "false", "참", "거짓"):
            return ast.BindPattern(name=tokens[0].value, span=self._span(tokens))
        if tokens and tokens[0].kind == "IDENT" and len(tokens) >= 3 and tokens[1].value == "(" and tokens[-1].value == ")":
            fields = self._parse_pattern_args(tokens[2:-1])
            return ast.StructPattern(struct_name=tokens[0].value, fields=fields, span=self._span(tokens))
        qualified = self._qualified_name(tokens)
        if qualified is not None:
            name, rest = qualified
            if "." in name:
                enum_name, case_name = name.split(".", 1)
                if rest and rest[0].value == "(" and rest[-1].value == ")":
                    inner = rest[1:-1]
                    if not inner:
                        return ast.EnumPattern(enum_name=enum_name, case_name=case_name, payload=None, binding=None, span=self._span(tokens))
                    if len(inner) == 1 and inner[0].kind == "IDENT":
                        return ast.EnumPattern(enum_name=enum_name, case_name=case_name, payload=None, binding=inner[0].value, span=self._span(tokens))
                    payload = self._parse_pattern_tokens(inner)
                    return ast.EnumPattern(enum_name=enum_name, case_name=case_name, payload=payload, binding=None, span=self._span(tokens))
                if not rest:
                    return ast.EnumPattern(enum_name=enum_name, case_name=case_name, payload=None, binding=None, span=self._span(tokens))
            if rest and rest[0].value == "(" and rest[-1].value == ")":
                fields = self._parse_pattern_args(rest[1:-1])
                return ast.StructPattern(struct_name=name, fields=fields, span=self._span(tokens))
        value = self._parse_expr_tokens(tokens)
        return ast.LiteralPattern(value=value, span=self._span(tokens))

    def _parse_pattern_args(self, tokens: List[Token]) -> List[ast.Pattern]:
        if not tokens:
            return []
        args: List[ast.Pattern] = []
        current: List[Token] = []
        depth = 0
        for tok in tokens:
            if tok.value == "(":
                depth += 1
            elif tok.value == ")":
                depth -= 1
            if tok.value == "," and depth == 0:
                if current:
                    args.append(self._parse_pattern_tokens(current))
                current = []
                continue
            current.append(tok)
        if current:
            args.append(self._parse_pattern_tokens(current))
        return args

    def _parse_expr_until(self, stop: str) -> ast.Expr:
        tokens: List[Token] = []
        while not self._peek_value(stop) and not self._peek(stop):
            tokens.append(self._advance())
        return self._parse_expr_tokens(tokens)

    def _parse_expr_tokens(self, tokens: List[Token]) -> ast.Expr:
        if not tokens:
            return ast.Name(value="__unit__")
        if tokens[0].value in ("try", "시도", "시도한다"):
            inner = self._parse_expr_tokens(tokens[1:])
            return ast.TryExpr(value=inner, span=self._span(tokens))
        if tokens[0].value == "빌려온다":
            mutable = tokens[2].value == "가변"
            inner = self._parse_expr_tokens(tokens[4:])
            return ast.BorrowExpr(value=inner, mutable=mutable, span=self._span(tokens))
        if tokens[0].value == "복사한다":
            inner = self._parse_expr_tokens(tokens[1:])
            return ast.CopyExpr(value=inner, span=self._span(tokens))
        return self._parse_expr_prec(tokens)

    def _parse_condition(self, tokens: List[Token]) -> ast.Expr:
        while tokens and tokens[-1].value in (":", "이면"):
            tokens = tokens[:-1]
        if tokens and tokens[0].value == "만약":
            tokens = tokens[1:]
        return self._parse_expr_tokens(tokens)

    def _parse_expr_prec(self, tokens: List[Token]) -> ast.Expr:
        return self._parse_logical_or(tokens)

    def _parse_logical_or(self, tokens: List[Token]) -> ast.Expr:
        idx = self._find_top_level(tokens, {"or", "||", "또는"})
        if idx is not None:
            left = self._parse_logical_or(tokens[:idx])
            right = self._parse_logical_and(tokens[idx + 1 :])
            return ast.LogicalOp(left=left, op="or", right=right, span=self._span(tokens))
        return self._parse_logical_and(tokens)

    def _parse_logical_and(self, tokens: List[Token]) -> ast.Expr:
        idx = self._find_top_level(tokens, {"and", "&&", "그리고"})
        if idx is not None:
            left = self._parse_logical_and(tokens[:idx])
            right = self._parse_comparison(tokens[idx + 1 :])
            return ast.LogicalOp(left=left, op="and", right=right, span=self._span(tokens))
        return self._parse_comparison(tokens)

    def _parse_comparison(self, tokens: List[Token]) -> ast.Expr:
        if self._looks_like_generic_call(tokens):
            return self._parse_add(tokens)
        if self._is_korean_compare(tokens):
            idx = self._find_top_level(tokens, {"보다"})
            if idx is not None and tokens[-1].value in ("크면", "작으면"):
                left = self._parse_add(tokens[:idx])
                right = self._parse_add(tokens[idx + 1 : -1])
                callee = "gt" if tokens[-1].value == "크면" else "lt"
                return ast.Call(callee=callee, args=[left, right], span=self._span(tokens))
        idx = self._find_top_level(tokens, {"==", "!=", ">=", "<=", ">", "<"})
        if idx is not None:
            left = self._parse_add(tokens[:idx])
            right = self._parse_add(tokens[idx + 1 :])
            callee = {"==": "eq", ">": "gt", "<": "lt", ">=": "ge", "<=": "le", "!=": "ne"}[tokens[idx].value]
            return ast.Call(callee=callee, args=[left, right], span=self._span(tokens))
        return self._parse_add(tokens)

    def _looks_like_generic_call(self, tokens: List[Token]) -> bool:
        if len(tokens) < 5:
            return False
        lt_idx = self._find_top_level(tokens, {"<"})
        if lt_idx is None:
            return False
        name_tokens = tokens[:lt_idx]
        if not name_tokens:
            return False
        if len(name_tokens) == 1:
            if name_tokens[0].kind != "IDENT":
                return False
        else:
            qualified = self._qualified_name(name_tokens)
            if qualified is None:
                return False
            _, rest = qualified
            if rest:
                return False
        depth = 0
        gt_idx = None
        for idx, tok in enumerate(tokens):
            if tok.value == "<":
                depth += 1
            elif tok.value == ">":
                depth -= 1
                if depth == 0:
                    gt_idx = idx
                    break
        if gt_idx is None:
            return False
        if gt_idx + 1 >= len(tokens):
            return False
        return tokens[gt_idx + 1].value == "(" and tokens[-1].value == ")"

    def _parse_add(self, tokens: List[Token]) -> ast.Expr:
        idx = self._find_top_level(tokens, {"+", "-"}, skip_unary=True)
        if idx is not None:
            left = self._parse_add(tokens[:idx])
            right = self._parse_mul(tokens[idx + 1 :])
            return ast.BinOp(left=left, op=tokens[idx].value, right=right, span=self._span(tokens))
        return self._parse_mul(tokens)

    def _parse_mul(self, tokens: List[Token]) -> ast.Expr:
        idx = self._find_top_level(tokens, {"*", "/"})
        if idx is not None:
            left = self._parse_mul(tokens[:idx])
            right = self._parse_unary(tokens[idx + 1 :])
            return ast.BinOp(left=left, op=tokens[idx].value, right=right, span=self._span(tokens))
        return self._parse_unary(tokens)

    def _parse_unary(self, tokens: List[Token]) -> ast.Expr:
        if tokens and tokens[0].value in ("+", "-"):
            value = self._parse_unary(tokens[1:])
            return ast.UnaryOp(op=tokens[0].value, value=value, span=self._span(tokens))
        return self._parse_primary(tokens)

    def _parse_primary(self, tokens: List[Token]) -> ast.Expr:
        if not tokens:
            return ast.Name(value="__unit__")
        if self._is_wrapped(tokens):
            return self._parse_expr_prec(tokens[1:-1])
        if len(tokens) == 1:
            return self._token_to_expr(tokens[0])
        generic_call = self._parse_generic_call(tokens)
        if generic_call is not None:
            return generic_call
        if tokens[0].kind == "IDENT" and tokens[1].value == "(" and tokens[-1].value == ")":
            args = self._parse_call_args(tokens[2:-1])
            return ast.Call(callee=tokens[0].value, args=args, span=self._span(tokens))
        qualified = self._qualified_name(tokens)
        if qualified is not None:
            name, rest = qualified
            if rest and rest[0].value == "(" and rest[-1].value == ")":
                args = self._parse_call_args(rest[1:-1])
                return ast.Call(callee=name, args=args, span=self._span(tokens))
            if not rest:
                return self._member_access_from_name(name, tokens)
        return self._token_to_expr(tokens[0])

    def _parse_generic_call(self, tokens: List[Token]) -> Optional[ast.Expr]:
        if len(tokens) < 5:
            return None
        lt_idx = self._find_top_level(tokens, {"<"})
        if lt_idx is None:
            return None
        name_tokens = tokens[:lt_idx]
        if not name_tokens:
            return None
        name = None
        if len(name_tokens) == 1 and name_tokens[0].kind == "IDENT":
            name = name_tokens[0].value
        else:
            qualified = self._qualified_name(name_tokens)
            if qualified is None:
                return None
            q_name, rest = qualified
            if rest:
                return None
            name = q_name
        gt_idx = self._find_top_level(tokens, {">"})
        if gt_idx is None or gt_idx <= lt_idx:
            return None
        if gt_idx + 1 >= len(tokens) or tokens[gt_idx + 1].value != "(" or tokens[-1].value != ")":
            return None
        arg_names: List[str] = []
        idx = lt_idx + 1
        while idx < gt_idx:
            tref, idx = self._parse_type_ref_tokens(tokens, idx)
            arg_names.append(self._mangle_type_ref(tref))
            if idx < gt_idx and tokens[idx].value == ",":
                idx += 1
                continue
            break
        if idx != gt_idx or not arg_names:
            return None
        callee = f"{name}__" + "__".join(arg_names)
        args = self._parse_call_args(tokens[gt_idx + 2 : -1])
        return ast.Call(callee=callee, args=args, span=self._span(tokens))

    def _mangle_type_ref(self, tref: ast.TypeRef) -> str:
        name = tref.name.replace(".", "__")
        if not tref.args:
            return name
        suffix = "__".join(self._mangle_type_ref(arg) for arg in tref.args)
        return f"{name}__{suffix}"

    def _is_wrapped(self, tokens: List[Token]) -> bool:
        if tokens[0].value != "(" or tokens[-1].value != ")":
            return False
        depth = 0
        for idx, tok in enumerate(tokens):
            if tok.value == "(":
                depth += 1
            elif tok.value == ")":
                depth -= 1
                if depth == 0 and idx != len(tokens) - 1:
                    return False
        return depth == 0

    def _qualified_name(self, tokens: List[Token]) -> Optional[tuple[str, List[Token]]]:
        if not tokens or tokens[0].kind != "IDENT":
            return None
        parts = [tokens[0].value]
        idx = 1
        while idx + 1 < len(tokens) and tokens[idx].value == "." and tokens[idx + 1].kind == "IDENT":
            parts.append(tokens[idx + 1].value)
            idx += 2
        if len(parts) == 1:
            return None
        return ".".join(parts), tokens[idx:]

    def _member_access_from_name(self, name: str, tokens: List[Token]) -> ast.Expr:
        parts = name.split(".")
        expr: ast.Expr = ast.Name(value=parts[0], span=self._span([tokens[0]]))
        for part in parts[1:]:
            expr = ast.MemberAccess(value=expr, name=part, span=self._span(tokens))
        return expr

    def _find_top_level(self, tokens: List[Token], values: set[str], skip_unary: bool = False) -> int | None:
        depth = 0
        for idx in range(len(tokens) - 1, -1, -1):
            tok = tokens[idx]
            if tok.value == ")":
                depth += 1
                continue
            if tok.value == "(":
                depth -= 1
                continue
            if depth != 0:
                continue
            if tok.value in values:
                if skip_unary and tok.value in ("+", "-") and (idx == 0 or tokens[idx - 1].value in ("(", ",") or tokens[idx - 1].kind == "OP"):
                    continue
                return idx
        return None

    def _parse_call_args(self, tokens: List[Token]) -> List[ast.Expr]:
        args: List[ast.Expr] = []
        current: List[Token] = []
        depth = 0
        angle_depth = 0
        for tok in tokens:
            if tok.value == "(":
                depth += 1
            elif tok.value == ")":
                depth -= 1
            elif tok.value == "<":
                angle_depth += 1
            elif tok.value == ">":
                angle_depth -= 1
            if tok.value == "," and depth == 0 and angle_depth == 0:
                args.append(self._parse_expr_tokens(current))
                current = []
            else:
                current.append(tok)
        if current:
            args.append(self._parse_expr_tokens(current))
        return args

    def _is_korean_compare(self, tokens: List[Token]) -> bool:
        values = [t.value for t in tokens]
        return "보다" in values and values[-1] in ("크면", "작으면")

    def _is_comparison(self, tokens: List[Token]) -> bool:
        return any(t.value in ("==", ">", "<", ">=", "<=", "!=") for t in tokens) or self._is_korean_compare(tokens)

    def _token_to_expr(self, token: Token) -> ast.Expr:
        if token.kind == "NUMBER":
            return ast.IntLit(value=int(token.value), span=self._span([token]))
        if token.kind == "STRING":
            return ast.StringLit(value=token.value, span=self._span([token]))
        if token.value in ("true", "false", "참", "거짓"):
            return ast.BoolLit(value=token.value in ("true", "참"), span=self._span([token]))
        return ast.Name(value=token.value, span=self._span([token]))

    def _consume_line(self) -> List[Token]:
        tokens: List[Token] = []
        while not self._peek("NEWLINE"):
            tokens.append(self._advance())
        return tokens

    def _extract_params(self, tokens: List[Token]) -> List[ast.Param]:
        if "받고" not in [t.value for t in tokens]:
            return []
        start = tokens.index(next(t for t in tokens if t.value == "은")) + 1
        end = tokens.index(next(t for t in tokens if t.value == "받고"))
        param_tokens = tokens[start:end]
        params: List[ast.Param] = []
        if not param_tokens:
            return params
        if len(param_tokens) == 1 and param_tokens[0].value == "아무것도":
            return params
        if ":" in [t.value for t in param_tokens]:
            name = param_tokens[0].value
            type_name = param_tokens[2].value
            params.append(ast.Param(name=name, type_ref=ast.TypeRef(type_name)))
        return params

    def _extract_return_type(self, tokens: List[Token]) -> Token:
        for idx, tok in enumerate(tokens):
            if tok.value in ("반환한다",):
                # Skip trailing particles
                j = idx - 1
                while j >= 0 and tokens[j].kind == "PART":
                    j -= 1
                return tokens[j]
        return tokens[-2]

    def _parse_korean_function_header(self, tokens: List[Token]) -> Tuple[Token, List[ast.Param], Token]:
        if (
            len(tokens) >= 3
            and tokens[0].value == "함수"
            and tokens[1].kind == "IDENT"
            and tokens[2].value == "정의"
        ):
            name = tokens[1]
            return_type = Token(kind="IDENT", value="unit", line=name.line, column=name.column)
            return name, [], return_type
        name = self._extract_name_after(tokens, "정의한다")
        if name is None:
            name = tokens[1]
        return_type = self._extract_return_type(tokens)
        params = self._extract_params(tokens)
        return name, params, return_type

    def _extract_name_after(self, tokens: List[Token], value: str) -> Optional[Token]:
        for idx, tok in enumerate(tokens):
            if tok.value == value and idx + 1 < len(tokens):
                return tokens[idx + 1]
        return None

    def _line_ends_with(self, value: str) -> bool:
        line = self._line_tokens()
        return line and line[-1].value == value

    def _line_contains(self, values: Tuple[str, ...]) -> bool:
        line = [t.value for t in self._line_tokens()]
        return all(v in line for v in values)

    def _line_tokens(self) -> List[Token]:
        idx = self.pos
        tokens: List[Token] = []
        while idx < len(self.tokens) and self.tokens[idx].kind != "NEWLINE":
            tokens.append(self.tokens[idx])
            idx += 1
        return tokens

    def _expect(self, kind: str, value: Optional[str] = None) -> Token:
        tok = self._advance()
        if tok.kind != kind:
            raise self._error(tok, f"Expected {kind}")
        if value is not None and tok.value != value:
            raise self._error(tok, f"Expected '{value}'")
        return tok

    def _expect_value(self, value: str) -> Token:
        tok = self._advance()
        if tok.value != value:
            raise self._error(tok, f"Expected '{value}'")
        return tok

    def _expect_ident(self) -> Token:
        tok = self._advance()
        if tok.kind not in ("IDENT",):
            raise self._error(tok, "Expected identifier")
        return tok

    def _skip_newlines(self) -> None:
        while self._peek("NEWLINE"):
            self._advance()

    def _peek(self, kind: str, value: Optional[str] = None) -> bool:
        tok = self._peek_token()
        if tok.kind != kind:
            return False
        if value is not None:
            return tok.value == value
        return True

    def _peek_value(self, value: str) -> bool:
        return self._peek_token().value == value

    def _peek_token(self) -> Token:
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _error(self, tok: Token, message: str) -> ParseError:
        return ParseError(f"L{tok.line}:{tok.column} {message}")

    def _span(self, tokens: List[Token]) -> Optional[Span]:
        if not tokens:
            return None
        start = tokens[0]
        end = tokens[-1]
        return Span(start.line, start.column, end.line, end.column + len(end.value))

    def _span_from_tokens(self, tokens: List[Token]) -> Optional[Span]:
        return self._span(tokens)


def parse(source: str) -> ast.Module:
    tokens = tokenize(source)
    return Parser(tokens).parse_module()


