from __future__ import annotations

from typing import Dict, List, Optional

from compiler_core import abi, ir


class CCodegen:
    def emit(self, module: ir.IRModule, extern_signatures: dict[str, tuple[str, list[str], str]] | None = None) -> str:
        self.externs = {ext.name for ext in module.externs}
        self.extern_return_types = {ext.name: ext.return_type for ext in module.externs}
        self.function_return_types = {func.name: func.return_type for func in module.functions}
        self.module_name = module.name
        self.extern_signatures = extern_signatures or {}
        self.structs = {s.name: s for s in module.structs}
        self.enums = {e.name: e for e in module.enums}
        lines: List[str] = []
        lines.append("#include <stdint.h>")
        lines.append('#include "rt.h"')
        lines.append("")
        for struct in module.structs:
            lines.append(f"typedef struct {self._struct_type_name(struct.name)} {{")
            for field in struct.fields:
                lines.append(f"  {self._map_type(field.type_name)} {field.name};")
            lines.append(f"}} {self._struct_type_name(struct.name)};")
        for enum in module.enums:
            lines.append(f"typedef struct {self._enum_type_name(enum.name)} {{")
            lines.append("  int64_t tag;")
            lines.append("  union {")
            for case in enum.cases:
                if case.payload:
                    lines.append(f"    {self._map_type(case.payload)} {case.name};")
            lines.append("  } data;")
            lines.append(f"}} {self._enum_type_name(enum.name)};")
        if module.structs or module.enums:
            lines.append("")
        for ext in module.externs:
            params = ", ".join([f"{self._map_type(p.type_name)} {p.name}" for p in ext.params])
            lines.append(f"extern {self._map_type(ext.return_type)} {ext.name}({params});")
        extern_used: Dict[str, tuple[list[str], str]] = {}
        for func in module.functions:
            for block in func.blocks:
                for instr in block.instructions:
                    if instr.op == "call" and "." in instr.args[0]:
                        callee = instr.args[0]
                        if callee in self.extern_signatures:
                            _, params, ret = self.extern_signatures[callee]
                            extern_used[callee] = (params, ret)
        for callee, (params, ret) in sorted(extern_used.items()):
            mod_name, fn_name = callee.split(".", 1)
            param_sig = ", ".join([f"{self._map_type(p)} arg_{idx}" for idx, p in enumerate(params)])
            lines.append(f"extern {self._map_type(ret)} {abi.mangle(mod_name, fn_name)}({param_sig});")
        if module.externs:
            lines.append("")
        for func in module.functions:
            if func.name == "main":
                continue
            ret_type = self._map_type(func.return_type)
            params = ", ".join([f"{self._map_type(p.type_name)} {p.name}" for p in func.params])
            lines.append(f"{ret_type} {abi.mangle(self.module_name, func.name)}({params});")
        if module.functions:
            lines.append("")
        for func in module.functions:
            lines.extend(self._emit_function(func))
            lines.append("")
        return "\n".join(lines)

    def _struct_type_name(self, name: str) -> str:
        mod_name, type_name = self._split_type_name(name)
        return f"daisy_struct_{mod_name}__{self._sanitize_type_name(type_name)}"

    def _enum_type_name(self, name: str) -> str:
        mod_name, type_name = self._split_type_name(name)
        return f"daisy_enum_{mod_name}__{self._sanitize_type_name(type_name)}"

    def _split_type_name(self, name: str) -> tuple[str, str]:
        if "." in name:
            mod, type_name = name.split(".", 1)
            return mod, type_name
        return self.module_name, name

    def _sanitize_type_name(self, name: str) -> str:
        return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)

    def _emit_function(self, func: ir.IRFunction) -> List[str]:
        lines: List[str] = []
        ret_type = self._map_type(func.return_type)
        params = ", ".join([f"{self._map_type(p.type_name)} {p.name}" for p in func.params])
        if func.name == "main":
            lines.append(f"{ret_type} {func.name}({params}) {{")
        else:
            lines.append(f"{ret_type} {abi.mangle(self.module_name, func.name)}({params}) {{")
        var_types: Dict[str, str] = {}
        owned_types: Dict[str, str] = {}
        released: Dict[str, bool] = {}
        escaped: Dict[str, bool] = {}
        for param in func.params:
            var_types[param.name] = param.type_name
        const_values: Dict[str, int] = {}
        release_targets: set[str] = set()
        escape_candidates: set[str] = set()
        for block in func.blocks:
            for instr in block.instructions:
                if instr.op == "const":
                    try:
                        const_values[instr.result] = int(instr.args[0])
                    except ValueError:
                        pass
                if instr.op == "release" and instr.args:
                    release_targets.add(instr.args[0])
                if instr.op == "call":
                    escape_candidates.update(instr.args[1:])
                if instr.op == "ret" and instr.args:
                    escape_candidates.add(instr.args[0])
        for block in func.blocks:
            for instr in block.instructions:
                lines.extend(
                    self._emit_instr(
                        instr,
                        var_types,
                        owned_types,
                        released,
                        escaped,
                        const_values,
                        release_targets,
                        escape_candidates,
                    )
                )
        if func.return_type == "unit":
            lines.append("  return 0;")
        lines.append("}")
        return lines

    def _emit_instr(
        self,
        instr: ir.Instr,
        var_types: Dict[str, str],
        owned_types: Dict[str, str],
        released: Dict[str, bool],
        escaped: Dict[str, bool],
        const_values: Dict[str, int],
        release_targets: set[str],
        escape_candidates: set[str],
    ) -> List[str]:
        out: List[str] = []
        if instr.op == "const":
            out.append(f"  int64_t {instr.result} = {instr.args[0]};")
            var_types[instr.result] = "int"
        elif instr.op == "const_str":
            out.append(f'  const char* {instr.result} = "{_escape(instr.args[0])}";')
            var_types[instr.result] = "string"
        elif instr.op == "assign":
            value = instr.args[0]
            if instr.result not in var_types:
                var_types[instr.result] = var_types.get(value, "int")
                out.append(f"  {self._map_type(var_types[instr.result])} {instr.result} = {value};")
            else:
                out.append(f"  {instr.result} = {value};")
            if value in owned_types and instr.result != value:
                owned_types[instr.result] = owned_types[value]
                del owned_types[value]
        elif instr.op == "add":
            out.append(f"  int64_t {instr.result} = {instr.args[0]} + {instr.args[1]};")
            var_types[instr.result] = "int"
        elif instr.op == "sub":
            out.append(f"  int64_t {instr.result} = {instr.args[0]} - {instr.args[1]};")
            var_types[instr.result] = "int"
        elif instr.op == "mul":
            out.append(f"  int64_t {instr.result} = {instr.args[0]} * {instr.args[1]};")
            var_types[instr.result] = "int"
        elif instr.op == "div":
            out.append(f"  int64_t {instr.result} = {instr.args[0]} / {instr.args[1]};")
            var_types[instr.result] = "int"
        elif instr.op == "neg":
            out.append(f"  int64_t {instr.result} = -{instr.args[0]};")
            var_types[instr.result] = "int"
        elif instr.op == "print":
            value = instr.args[0]
            vtype = var_types.get(value, "int")
            if vtype == "string":
                out.append(f"  daisy_print_str({value});")
            else:
                out.append(f"  daisy_print_int({value});")
        elif instr.op == "ret":
            if instr.args and instr.args[0] in owned_types:
                escaped[instr.args[0]] = True
            out.extend(self._emit_cleanup(owned_types, released, escaped))
            out.append(f"  return {instr.args[0]};")
        elif instr.op == "buf_create":
            size_arg = instr.args[0]
            size_const = const_values.get(size_arg)
            if (
                size_const is not None
                and size_const > 0
                and instr.result not in release_targets
                and instr.result not in escape_candidates
            ):
                out.append(f"  uint8_t {instr.result}_stack[{size_const}];")
                out.append(f"  DaisyBuffer {instr.result} = (DaisyBuffer){{ {instr.result}_stack, {size_const} }};")
                var_types[instr.result] = "buffer"
                owned_types[instr.result] = "buffer_stack"
            else:
                out.append(f"  DaisyBuffer {instr.result} = daisy_buffer_create({instr.args[0]});")
                var_types[instr.result] = "buffer"
                owned_types[instr.result] = "buffer"
        elif instr.op == "buf_borrow":
            out.append(
                f"  DaisyView {instr.result} = daisy_buffer_borrow(&{instr.args[0]}, {instr.args[1]}, {instr.args[2]}, {instr.args[3]});"
            )
            var_types[instr.result] = "view"
        elif instr.op == "release":
            target = instr.args[0]
            t = var_types.get(target)
            if t == "buffer":
                out.append(f"  daisy_buffer_release(&{target});")
                released[target] = True
            elif t == "tensor":
                out.append(f"  daisy_tensor_release(&{target});")
                released[target] = True
            elif t == "channel":
                out.append(f"  daisy_channel_release({target});")
                released[target] = True
            elif t == "string":
                out.append(f"  daisy_str_release({target});")
                released[target] = True
            elif t == "vec":
                out.append(f"  daisy_vec_release({target});")
                released[target] = True
        elif instr.op == "struct_new":
            struct_name = instr.args[0]
            args = instr.args[1:]
            c_type = self._map_type(struct_name)
            out.append(f"  {c_type} {instr.result};")
            fields = self.structs.get(struct_name)
            if fields:
                for idx, field in enumerate(fields.fields):
                    if idx < len(args):
                        out.append(f"  {instr.result}.{field.name} = {args[idx]};")
            var_types[instr.result] = struct_name
        elif instr.op == "struct_get":
            base, field = instr.args
            base_type = var_types.get(base)
            if base_type and base_type in self.structs:
                c_type = self._map_type(self._struct_field_type(base_type, field) or "int")
            else:
                c_type = "int64_t"
            out.append(f"  {c_type} {instr.result} = {base}.{field};")
            var_types[instr.result] = self._struct_field_type(base_type, field) or "int"
        elif instr.op == "struct_set":
            base, field, value = instr.args
            out.append(f"  {base}.{field} = {value};")
        elif instr.op == "enum_make":
            enum_name, case_name = instr.args[0], instr.args[1]
            payload = instr.args[2] if len(instr.args) > 2 else None
            enum_type = self._map_type(enum_name)
            out.append(f"  {enum_type} {instr.result};")
            out.append(f"  {instr.result}.tag = {self._enum_case_index(enum_name, case_name)};")
            if payload:
                out.append(f"  {instr.result}.data.{case_name} = {payload};")
            var_types[instr.result] = enum_name
        elif instr.op == "enum_payload":
            enum_val, case_name = instr.args
            enum_type = var_types.get(enum_val)
            payload_type = self._enum_case_payload_type(enum_type, case_name) if enum_type else None
            c_type = self._map_type(payload_type or "int")
            out.append(f"  {c_type} {instr.result} = {enum_val}.data.{case_name};")
            var_types[instr.result] = payload_type or "int"
        elif instr.op == "call":
            callee = instr.args[0]
            args = instr.args[1:]
            for arg in args:
                if var_types.get(arg) in ("buffer", "tensor", "channel", "string", "vec"):
                    escaped[arg] = True
            if callee == "int_add":
                out.append(f"  int64_t {instr.result} = {args[0]} + {args[1]};")
                var_types[instr.result] = "int"
            elif callee == "int_sub":
                out.append(f"  int64_t {instr.result} = {args[0]} - {args[1]};")
                var_types[instr.result] = "int"
            elif callee == "gt":
                out.append(f"  int64_t {instr.result} = ({args[0]} > {args[1]});")
                var_types[instr.result] = "int"
            elif callee == "lt":
                out.append(f"  int64_t {instr.result} = ({args[0]} < {args[1]});")
                var_types[instr.result] = "int"
            elif callee == "eq":
                out.append(f"  int64_t {instr.result} = ({args[0]} == {args[1]});")
                var_types[instr.result] = "int"
            elif callee == "ge":
                out.append(f"  int64_t {instr.result} = ({args[0]} >= {args[1]});")
                var_types[instr.result] = "int"
            elif callee == "le":
                out.append(f"  int64_t {instr.result} = ({args[0]} <= {args[1]});")
                var_types[instr.result] = "int"
            elif callee == "ne":
                out.append(f"  int64_t {instr.result} = ({args[0]} != {args[1]});")
                var_types[instr.result] = "int"
            elif callee == "tensor_matmul":
                if len(args) == 0:
                    out.append(f"  DaisyTensor {instr.result} = daisy_tensor_create(1, 1);")
                elif len(args) == 2:
                    out.append(f"  DaisyTensor {instr.result} = daisy_tensor_matmul({', '.join(args)});")
                else:
                    raise RuntimeError("tensor_matmul expects 0 or 2 args")
                var_types[instr.result] = "tensor"
                owned_types[instr.result] = "tensor"
            elif callee == "vec_new":
                out.append(f"  DaisyVec* {instr.result} = daisy_vec_new();")
                var_types[instr.result] = "vec"
                owned_types[instr.result] = "vec"
            elif callee == "vec_push":
                if instr.result:
                    out.append(f"  int64_t {instr.result} = 0;")
                    var_types[instr.result] = "int"
                out.append(f"  daisy_vec_push({args[0]}, {args[1]});")
            elif callee == "vec_len":
                out.append(f"  int64_t {instr.result} = daisy_vec_len({args[0]});")
                var_types[instr.result] = "int"
            elif callee == "vec_get":
                out.append(f"  int64_t {instr.result} = daisy_vec_get({args[0]}, {args[1]});")
                var_types[instr.result] = "int"
            elif callee == "vec_release":
                if instr.result:
                    out.append(f"  int64_t {instr.result} = 0;")
                    var_types[instr.result] = "int"
                out.append(f"  daisy_vec_release({args[0]});")
            elif callee == "str_len":
                out.append(f"  int64_t {instr.result} = daisy_str_len({args[0]});")
                var_types[instr.result] = "int"
            elif callee == "str_char_at":
                out.append(f"  int64_t {instr.result} = daisy_str_char_at({args[0]}, {args[1]});")
                var_types[instr.result] = "int"
            elif callee == "str_find_char":
                out.append(f"  int64_t {instr.result} = daisy_str_find_char({args[0]}, {args[1]}, {args[2]});")
                var_types[instr.result] = "int"
            elif callee == "str_starts_with":
                out.append(f"  int64_t {instr.result} = daisy_str_starts_with({args[0]}, {args[1]});")
                var_types[instr.result] = "int"
            elif callee == "str_to_int":
                out.append(f"  int64_t {instr.result} = daisy_str_to_int({args[0]});")
                var_types[instr.result] = "int"
            elif callee == "str_substr":
                out.append(f"  const char* {instr.result} = daisy_str_substr({args[0]}, {args[1]}, {args[2]});")
                var_types[instr.result] = "string"
                owned_types[instr.result] = "string"
            elif callee == "str_trim":
                out.append(f"  const char* {instr.result} = daisy_str_trim({args[0]});")
                var_types[instr.result] = "string"
                owned_types[instr.result] = "string"
            elif callee == "str_escape_json":
                out.append(f"  const char* {instr.result} = daisy_str_escape_json({args[0]});")
                var_types[instr.result] = "string"
                owned_types[instr.result] = "string"
            elif callee == "str_concat":
                out.append(f"  const char* {instr.result} = daisy_str_concat({args[0]}, {args[1]});")
                var_types[instr.result] = "string"
                owned_types[instr.result] = "string"
            elif callee == "str_release":
                if instr.result:
                    out.append(f"  int64_t {instr.result} = 0;")
                    var_types[instr.result] = "int"
                out.append(f"  daisy_str_release({args[0]});")
                if args and args[0] in owned_types:
                    released[args[0]] = True
                    del owned_types[args[0]]
            elif callee == "int_to_str":
                out.append(f"  const char* {instr.result} = daisy_int_to_str({args[0]});")
                var_types[instr.result] = "string"
                owned_types[instr.result] = "string"
            elif callee == "file_read":
                out.append(f"  const char* {instr.result} = daisy_file_read({args[0]});")
                var_types[instr.result] = "string"
                owned_types[instr.result] = "string"
            elif callee == "file_write":
                out.append(f"  int64_t {instr.result} = daisy_file_write({args[0]}, {args[1]});")
                var_types[instr.result] = "int"
            elif callee == "module_load":
                out.append(f"  const char* {instr.result} = daisy_module_load({args[0]});")
                var_types[instr.result] = "string"
                owned_types[instr.result] = "string"
            elif callee == "error_last":
                out.append(f"  const char* {instr.result} = daisy_error_last();")
                var_types[instr.result] = "string"
            elif callee == "error_clear":
                if instr.result:
                    out.append(f"  int64_t {instr.result} = 0;")
                    var_types[instr.result] = "int"
                out.append("  daisy_error_clear();")
            elif callee == "panic":
                if instr.result:
                    out.append(f"  int64_t {instr.result} = 0;")
                    var_types[instr.result] = "int"
                out.append(f"  daisy_panic({args[0]});")
            elif callee == "channel":
                out.append(f"  DaisyChannel* {instr.result} = daisy_channel_create();")
                var_types[instr.result] = "channel"
                owned_types[instr.result] = "channel"
            elif callee == "send":
                if instr.result:
                    out.append(f"  int64_t {instr.result} = 0;")
                    var_types[instr.result] = "int"
                out.append(f"  daisy_channel_send({args[0]}, {args[1]});")
            elif callee == "recv":
                out.append(f"  int64_t {instr.result} = daisy_channel_recv({args[0]});")
                var_types[instr.result] = "int"
            elif callee == "channel_close":
                if instr.result:
                    out.append(f"  int64_t {instr.result} = 0;")
                    var_types[instr.result] = "int"
                out.append(f"  daisy_channel_close({args[0]});")
            elif callee == "spawn":
                if instr.result:
                    out.append(f"  int64_t {instr.result} = 0;")
                    var_types[instr.result] = "int"
                if len(args) == 1:
                    out.append(f"  daisy_spawn((void*){abi.mangle(self.module_name, args[0])});")
                elif len(args) == 2:
                    out.append(f"  daisy_spawn_with_channel((void*){abi.mangle(self.module_name, args[0])}, {args[1]});")
            else:
                if "." in callee:
                    mod_name, fn_name = callee.split(".", 1)
                    call_name = abi.mangle(mod_name, fn_name)
                else:
                    call_name = callee if callee in self.externs else abi.mangle(self.module_name, callee)
                return_type = self.function_return_types.get(callee) or self.extern_return_types.get(callee)
                if return_type is None and "." in callee:
                    return_type = self.extern_signatures.get(callee, (None, [], None))[2]
                c_type = self._map_type(return_type) if return_type else "int64_t"
                out.append(f"  {c_type} {instr.result} = {call_name}({', '.join(args)});")
                if return_type:
                    var_types[instr.result] = return_type
                    if return_type in ("string", "buffer", "tensor", "channel", "vec"):
                        owned_types[instr.result] = return_type
                else:
                    var_types[instr.result] = "int"
        elif instr.op == "borrow":
            out.append(f"  DaisyView {instr.result} = daisy_view_borrow({instr.args[0]}, {instr.args[1]});")
            var_types[instr.result] = "view"
        elif instr.op == "enum_tag":
            out.append(f"  int64_t {instr.result} = {instr.args[0]}.tag;")
            var_types[instr.result] = "int"
        elif instr.op == "loop_begin":
            out.append(f"  while ({instr.args[0]} < {instr.args[1]}) {{")
        elif instr.op == "inc":
            out.append(f"  {instr.args[0]} += 1;")
        elif instr.op == "loop_end":
            out.append("  }")
        elif instr.op == "if_begin":
            out.append(f"  if ({instr.args[0]}) {{")
        elif instr.op == "if_else":
            out.append("  } else {")
        elif instr.op == "if_end":
            out.append("  }")
        elif instr.op == "while_begin":
            out.append(f"  while ({instr.args[0]}) {{")
        elif instr.op == "while_end":
            out.append("  }")
        elif instr.op == "break":
            out.append("  break;")
        elif instr.op == "continue":
            out.append("  continue;")
        else:
            raise RuntimeError(f"Unsupported IR op: {instr.op}")
        return out

    def _map_type(self, name: str) -> str:
        if name in self.structs:
            return self._struct_type_name(name)
        if name in self.enums:
            return self._enum_type_name(name)
        if name in ("int", "bool"):
            return "int64_t"
        if name == "string":
            return "const char*"
        if name == "buffer":
            return "DaisyBuffer"
        if name == "view":
            return "DaisyView"
        if name == "tensor":
            return "DaisyTensor"
        if name == "channel":
            return "DaisyChannel*"
        if name == "vec":
            return "DaisyVec*"
        if name in ("unit", "void"):
            return "int64_t"
        return "int64_t"

    def _struct_field_type(self, struct_name: str | None, field: str) -> Optional[str]:
        if not struct_name or struct_name not in self.structs:
            return None
        for f in self.structs[struct_name].fields:
            if f.name == field:
                return f.type_name
        return None

    def _enum_case_index(self, enum_name: str, case_name: str) -> int:
        enum = self.enums.get(enum_name)
        if not enum:
            return 0
        for idx, case in enumerate(enum.cases):
            if case.name == case_name:
                return idx
        return 0

    def _enum_case_payload_type(self, enum_name: Optional[str], case_name: str) -> Optional[str]:
        if not enum_name:
            return None
        enum = self.enums.get(enum_name)
        if not enum:
            return None
        for case in enum.cases:
            if case.name == case_name:
                return case.payload
        return None

    def _emit_cleanup(
        self,
        owned_types: Dict[str, str],
        released: Dict[str, bool],
        escaped: Dict[str, bool],
    ) -> List[str]:
        out: List[str] = []
        for name, t in list(owned_types.items()):
            if released.get(name):
                continue
            if escaped.get(name):
                continue
            if t == "buffer_stack":
                released[name] = True
                continue
            if t == "buffer":
                out.append(f"  daisy_buffer_release(&{name});")
            elif t == "tensor":
                out.append(f"  daisy_tensor_release(&{name});")
            elif t == "channel":
                out.append(f"  daisy_channel_release({name});")
            elif t == "string":
                out.append(f"  daisy_str_release({name});")
            elif t == "vec":
                out.append(f"  daisy_vec_release({name});")
            released[name] = True
        return out


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


