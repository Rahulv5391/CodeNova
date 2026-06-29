"""
AST Extractor — Stage 1 of the ingestion pipeline.

Uses tree-sitter to parse source files into structured ASTMetadata objects
BEFORE chunking. Produces:
  - Function/method definitions with signatures, docstrings, decorators,
    return types, complexity, and call lists
  - Class definitions with inheritance, fields, method lists
  - Import/dependency edges
  - Top-level global names

Supported: Python · JavaScript · TypeScript · Java · Go
Fallback:  empty metadata (no crash) for all other languages

Output feeds:
  a) chunker.py     → symbol-aligned chunk boundaries
  b) graph_store.py → Neo4j nodes + relationships
"""
from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

# ── Language loader ────────────────────────────────────────────────────────────

def _load_languages() -> dict:
    from tree_sitter import Language
    out: dict = {}
    _try_load(out, "python",     lambda: __import__("tree_sitter_python").language(),     Language)
    _try_load(out, "javascript", lambda: __import__("tree_sitter_javascript").language(), Language)
    _try_load(out, "typescript", lambda: __import__("tree_sitter_typescript").language_typescript(), Language)
    _try_load(out, "tsx",        lambda: __import__("tree_sitter_typescript").language_tsx(),        Language)
    _try_load(out, "java",       lambda: __import__("tree_sitter_java").language(),       Language)
    _try_load(out, "go",         lambda: __import__("tree_sitter_go").language(),         Language)
    return out

def _try_load(out: dict, name: str, ptr_fn, Language_cls) -> None:
    try:
        out[name] = Language_cls(ptr_fn())
    except Exception as exc:
        logger.warning(f"tree-sitter {name} unavailable: {exc}")

_LANGUAGES: dict | None = None

def _langs() -> dict:
    global _LANGUAGES
    if _LANGUAGES is None:
        _LANGUAGES = _load_languages()
    return _LANGUAGES


# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class ParameterInfo:
    name: str
    type_hint: str | None = None
    default_value: str | None = None


@dataclass
class FunctionInfo:
    name: str
    file_path: str
    start_line: int
    end_line: int
    parameters: list[ParameterInfo] = field(default_factory=list)
    return_type: str | None = None
    docstring: str | None = None
    decorators: list[str] = field(default_factory=list)
    is_async: bool = False
    is_method: bool = False
    parent_class: str | None = None
    calls: list[str] = field(default_factory=list)
    complexity: int = 1
    body: str = ""


@dataclass
class ClassInfo:
    name: str
    file_path: str
    start_line: int
    end_line: int
    base_classes: list[str] = field(default_factory=list)
    docstring: str | None = None
    decorators: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    body: str = ""


@dataclass
class ImportInfo:
    module: str
    names: list[str] = field(default_factory=list)
    alias: str | None = None
    is_from_import: bool = False
    line: int = 0


@dataclass
class ASTMetadata:
    file_path: str
    language: str
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    globals: list[str] = field(default_factory=list)
    total_functions: int = 0
    total_classes: int = 0
    parse_errors: list[str] = field(default_factory=list)


# ── Node helpers ───────────────────────────────────────────────────────────────

def _text(src: bytes, node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

def _lines_of(src: str, node) -> str:
    rows = src.splitlines()
    return "\n".join(rows[node.start_point[0] : node.end_point[0] + 1])

def _complexity(node) -> int:
    BRANCH = {
        "if_statement", "elif_clause", "for_statement", "while_statement",
        "with_statement", "try_statement", "except_clause",
        "conditional_expression", "switch_statement", "case_clause",
        "catch_clause", "ternary_expression",
    }
    count = [1]
    def _walk(n):
        if n.type in BRANCH:
            count[0] += 1
        for c in n.children:
            _walk(c)
    _walk(node)
    return count[0]

def _calls(src: bytes, node) -> list[str]:
    result: list[str] = []
    def _walk(n):
        if n.type == "call":
            fn_node = n.child_by_field_name("function")
            if fn_node:
                name = _text(src, fn_node).split("(")[0].split(".")[-1]
                if name.isidentifier():
                    result.append(name)
        for c in n.children:
            _walk(c)
    _walk(node)
    return list(dict.fromkeys(result))[:20]   # deduplicate, cap at 20


# ── Python ─────────────────────────────────────────────────────────────────────

def _py_docstring(body_node, src: bytes) -> str | None:
    if not body_node:
        return None
    for child in body_node.children:
        if child.type == "expression_statement":
            sub = child.children[0] if child.children else None
            if sub and sub.type in ("string", "concatenated_string"):
                raw = _text(src, sub)
                return raw.strip('"""').strip("'''").strip('"').strip("'").strip()
    return None

def _py_params(params_node, src: bytes) -> list[ParameterInfo]:
    if not params_node:
        return []
    out: list[ParameterInfo] = []
    skip = {"self", "cls", "(", ")", ",", "*", "**", "/"}
    for child in params_node.children:
        t = child.type
        if t == "identifier":
            name = _text(src, child)
            if name not in skip:
                out.append(ParameterInfo(name=name))
        elif t == "typed_parameter":
            # identifier ':' type
            name = next((_text(src, c) for c in child.children if c.type == "identifier"), "")
            ptype = next((_text(src, c) for c in child.children if c.type == "type"), None)
            if name and name not in skip:
                out.append(ParameterInfo(name=name, type_hint=ptype))
        elif t == "typed_default_parameter":
            name = next((_text(src, c) for c in child.children if c.type == "identifier"), "")
            ptype = next((_text(src, c) for c in child.children if c.type == "type"), None)
            # default is after '='
            children = list(child.children)
            default = None
            for i, c in enumerate(children):
                if not c.is_named and _text(src, c) == "=" and i + 1 < len(children):
                    default = _text(src, children[i + 1])
            if name and name not in skip:
                out.append(ParameterInfo(name=name, type_hint=ptype, default_value=default))
        elif t == "default_parameter":
            name = next((_text(src, c) for c in child.children if c.type == "identifier"), "")
            if name and name not in skip:
                out.append(ParameterInfo(name=name))
    return out

def _py_decorators(decorated_node, src: bytes) -> list[str]:
    return [_text(src, c) for c in decorated_node.children if c.type == "decorator"]

def _py_function(fn_node, src: bytes, src_str: str, file_path: str,
                 parent_class: str | None = None,
                 decorators: list[str] | None = None) -> FunctionInfo:
    name_node   = fn_node.child_by_field_name("name")
    params_node = fn_node.child_by_field_name("parameters")
    ret_node    = fn_node.child_by_field_name("return_type")
    body_node   = fn_node.child_by_field_name("body")
    is_async    = any(not c.is_named and _text(src, c) == "async" for c in fn_node.children)
    return FunctionInfo(
        name         = _text(src, name_node) if name_node else "<anonymous>",
        file_path    = file_path,
        start_line   = fn_node.start_point[0],
        end_line     = fn_node.end_point[0],
        parameters   = _py_params(params_node, src),
        return_type  = _text(src, ret_node) if ret_node else None,
        docstring    = _py_docstring(body_node, src),
        decorators   = decorators or [],
        is_async     = is_async,
        is_method    = parent_class is not None,
        parent_class = parent_class,
        calls        = _calls(src, fn_node),
        complexity   = _complexity(fn_node),
        body         = _lines_of(src_str, fn_node),
    )

def _extract_python(src_str: str, file_path: str) -> ASTMetadata:
    from tree_sitter import Parser
    meta = ASTMetadata(file_path=file_path, language="python")
    if "python" not in _langs():
        meta.parse_errors.append("tree-sitter Python unavailable")
        return meta

    src = src_str.encode("utf-8", errors="replace")
    parser = Parser(_langs()["python"])
    tree = parser.parse(src)
    root = tree.root_node

    if root.has_error:
        meta.parse_errors.append("Syntax errors detected (partial parse)")

    for node in root.children:
        actual, decorators = node, []
        if node.type == "decorated_definition":
            decorators = _py_decorators(node, src)
            actual = next((c for c in node.children
                           if c.type in ("function_definition", "class_definition")), node)

        if actual.type in ("function_definition",):
            meta.functions.append(_py_function(actual, src, src_str, file_path, decorators=decorators))

        elif actual.type == "class_definition":
            name_node  = actual.child_by_field_name("name")
            args_node  = actual.child_by_field_name("superclasses")
            body_node  = actual.child_by_field_name("body")
            class_name = _text(src, name_node) if name_node else "<anonymous>"
            bases = ([_text(src, c) for c in args_node.children
                      if c.is_named and c.type not in (",", "(", ")")]
                     if args_node else [])
            methods: list[str] = []
            fields: list[str] = []
            if body_node:
                for child in body_node.children:
                    child_actual, child_dec = child, []
                    if child.type == "decorated_definition":
                        child_dec = _py_decorators(child, src)
                        child_actual = next((c for c in child.children
                                             if c.type == "function_definition"), child)
                    if child_actual.type == "function_definition":
                        fn = _py_function(child_actual, src, src_str, file_path,
                                          parent_class=class_name, decorators=child_dec)
                        meta.functions.append(fn)
                        methods.append(fn.name)
                    elif child_actual.type in ("expression_statement", "assignment"):
                        t = _text(src, child_actual).split("=")[0].strip().split(":")[0].strip()
                        if t.isidentifier():
                            fields.append(t)
            meta.classes.append(ClassInfo(
                name         = class_name,
                file_path    = file_path,
                start_line   = actual.start_point[0],
                end_line     = actual.end_point[0],
                base_classes = bases,
                docstring    = _py_docstring(body_node, src),
                decorators   = decorators,
                methods      = methods,
                fields       = fields,
                body         = _lines_of(src_str, actual),
            ))

        elif actual.type == "import_statement":
            # import os  OR  import os as operating_system
            named = [c for c in actual.children if c.is_named]
            for c in named:
                if c.type == "dotted_name":
                    meta.imports.append(ImportInfo(module=_text(src, c), line=actual.start_point[0]))
                elif c.type == "aliased_import":
                    parts = [x for x in c.children if x.is_named]
                    module = _text(src, parts[0]) if parts else ""
                    alias  = _text(src, parts[-1]) if len(parts) > 1 else None
                    meta.imports.append(ImportInfo(module=module, alias=alias, line=actual.start_point[0]))

        elif actual.type == "import_from_statement":
            # from pathlib import Path, PurePath
            # first dotted_name = module, subsequent = imported names
            named = [c for c in actual.children if c.is_named and c.type == "dotted_name"]
            if named:
                module = _text(src, named[0])
                imported_names = [_text(src, c) for c in named[1:]]
                meta.imports.append(ImportInfo(
                    module=module, names=imported_names,
                    is_from_import=True, line=actual.start_point[0],
                ))

        elif actual.type == "expression_statement":
            t = _text(src, actual).split("=")[0].strip()
            if t.isidentifier() and t.isupper():    # only CONSTANTS
                meta.globals.append(t)

    meta.total_functions = len(meta.functions)
    meta.total_classes   = len(meta.classes)
    return meta


# ── JavaScript / TypeScript ────────────────────────────────────────────────────

def _js_params(params_node, src: bytes) -> list[ParameterInfo]:
    if not params_node:
        return []
    out: list[ParameterInfo] = []
    for child in params_node.children:
        t = child.type
        if t == "identifier":
            out.append(ParameterInfo(name=_text(src, child)))
        elif t == "required_parameter":
            name   = next((_text(src, c) for c in child.children if c.type == "identifier"), "")
            tnode  = next((c for c in child.children if c.type == "type_annotation"), None)
            out.append(ParameterInfo(name=name, type_hint=_text(src, tnode).lstrip(":").strip() if tnode else None))
        elif t in ("optional_parameter", "assignment_pattern"):
            name = next((_text(src, c) for c in child.children if c.type == "identifier"), "")
            if name:
                out.append(ParameterInfo(name=name))
        elif t == "rest_pattern":
            name = next((_text(src, c) for c in child.children if c.type == "identifier"), "")
            if name:
                out.append(ParameterInfo(name="..." + name))
    return [p for p in out if p.name and p.name != "this"]

def _js_function(fn_node, src: bytes, src_str: str, file_path: str,
                 parent_class: str | None = None, name_override: str | None = None) -> FunctionInfo:
    name_node   = fn_node.child_by_field_name("name")
    params_node = fn_node.child_by_field_name("parameters")
    ret_node    = fn_node.child_by_field_name("return_type")
    is_async    = any(not c.is_named and _text(src, c) == "async" for c in fn_node.children)
    return FunctionInfo(
        name         = name_override or (_text(src, name_node) if name_node else "<anonymous>"),
        file_path    = file_path,
        start_line   = fn_node.start_point[0],
        end_line     = fn_node.end_point[0],
        parameters   = _js_params(params_node, src),
        return_type  = _text(src, ret_node).lstrip(":").strip() if ret_node else None,
        is_async     = is_async,
        is_method    = parent_class is not None,
        parent_class = parent_class,
        calls        = _calls(src, fn_node),
        complexity   = _complexity(fn_node),
        body         = _lines_of(src_str, fn_node),
    )

def _extract_js_ts(src_str: str, file_path: str, language: str) -> ASTMetadata:
    from tree_sitter import Parser
    meta = ASTMetadata(file_path=file_path, language=language)
    lang_key = "typescript" if language in ("typescript", "tsx") else "javascript"
    if lang_key not in _langs():
        meta.parse_errors.append(f"tree-sitter {language} unavailable")
        return meta

    src = src_str.encode("utf-8", errors="replace")
    parser = Parser(_langs()[lang_key])
    tree = parser.parse(src)
    root = tree.root_node

    FN_TYPES = ("function_declaration", "generator_function_declaration")
    CLASS_TYPES = ("class_declaration",)

    def walk(node, parent_class: str | None = None):
        t = node.type

        if t == "export_statement":
            for child in node.children:
                walk(child, parent_class)

        elif t in FN_TYPES:
            meta.functions.append(_js_function(node, src, src_str, file_path, parent_class))

        elif t == "lexical_declaration":
            # const fn = (x) => ..., const fn = function() {}
            for declarator in node.children:
                if declarator.type == "variable_declarator":
                    val  = declarator.child_by_field_name("value")
                    name = declarator.child_by_field_name("name")
                    if val and val.type in ("arrow_function", "function"):
                        fn = _js_function(val, src, src_str, file_path, parent_class,
                                          name_override=_text(src, name) if name else None)
                        meta.functions.append(fn)

        elif t in CLASS_TYPES:
            name_node = node.child_by_field_name("name")
            class_name = _text(src, name_node) if name_node else "<anonymous>"
            heritage   = node.child_by_field_name("heritage")
            bases = ([_text(src, c) for c in heritage.children
                      if c.is_named and c.type not in (",",)]
                     if heritage else [])
            body  = node.child_by_field_name("body")
            methods: list[str] = []
            if body:
                for child in body.children:
                    if child.type == "method_definition":
                        fn = _js_function(child, src, src_str, file_path, class_name)
                        meta.functions.append(fn)
                        methods.append(fn.name)
            meta.classes.append(ClassInfo(
                name=class_name, file_path=file_path,
                start_line=node.start_point[0], end_line=node.end_point[0],
                base_classes=bases, methods=methods,
                body=_lines_of(src_str, node),
            ))

        elif t == "import_statement":
            source = node.child_by_field_name("source")
            mod    = _text(src, source).strip("'\"") if source else ""
            names: list[str] = []
            for child in node.children:
                if child.type == "import_clause":
                    for sub in child.children:
                        if sub.type == "named_imports":
                            for spec in sub.children:
                                if spec.type == "import_specifier":
                                    names.append(_text(src, spec))
                        elif sub.type == "identifier":
                            names.append(_text(src, sub))
            meta.imports.append(ImportInfo(module=mod, names=names, is_from_import=True, line=node.start_point[0]))

    for child in root.children:
        walk(child)

    meta.total_functions = len(meta.functions)
    meta.total_classes   = len(meta.classes)
    return meta


# ── Java ───────────────────────────────────────────────────────────────────────

def _extract_java(src_str: str, file_path: str) -> ASTMetadata:
    from tree_sitter import Parser
    meta = ASTMetadata(file_path=file_path, language="java")
    if "java" not in _langs():
        meta.parse_errors.append("tree-sitter Java unavailable")
        return meta

    src = src_str.encode("utf-8", errors="replace")
    parser = Parser(_langs()["java"])
    tree = parser.parse(src)
    root = tree.root_node

    def walk(node, parent_class: str | None = None):
        t = node.type

        if t == "import_declaration":
            raw = _text(src, node).replace("import", "").replace(";", "").strip()
            meta.imports.append(ImportInfo(module=raw, line=node.start_point[0]))

        elif t == "class_declaration":
            name_node  = node.child_by_field_name("name")
            class_name = _text(src, name_node) if name_node else "<anonymous>"
            super_node = node.child_by_field_name("superclass")
            ifaces     = node.child_by_field_name("interfaces")
            bases: list[str] = []
            if super_node:
                bases.append(_text(src, super_node).replace("extends", "").strip())
            if ifaces:
                bases += [_text(src, c) for c in ifaces.children
                          if c.is_named and _text(src, c) not in ("implements",)]
            body  = node.child_by_field_name("body")
            methods: list[str] = []
            fields_: list[str] = []
            if body:
                for child in body.children:
                    if child.type == "method_declaration":
                        fn = _java_method(child, src, src_str, file_path, class_name)
                        meta.functions.append(fn)
                        methods.append(fn.name)
                    elif child.type == "field_declaration":
                        for decl in child.children:
                            if decl.type == "variable_declarator":
                                fields_.append(_text(src, decl).split("=")[0].strip())
            meta.classes.append(ClassInfo(
                name=class_name, file_path=file_path,
                start_line=node.start_point[0], end_line=node.end_point[0],
                base_classes=bases, methods=methods, fields=fields_,
                body=_lines_of(src_str, node),
            ))

        else:
            for child in node.children:
                walk(child, parent_class)

    def _java_method(m_node, src, src_str, file_path, class_name) -> FunctionInfo:
        name_node   = m_node.child_by_field_name("name")
        params_node = m_node.child_by_field_name("parameters")
        ret_node    = m_node.child_by_field_name("type")
        params: list[ParameterInfo] = []
        if params_node:
            for child in params_node.children:
                if child.type == "formal_parameter":
                    ptype = child.child_by_field_name("type")
                    pname = child.child_by_field_name("name")
                    params.append(ParameterInfo(
                        name=_text(src, pname) if pname else "",
                        type_hint=_text(src, ptype) if ptype else None,
                    ))
        return FunctionInfo(
            name         = _text(src, name_node) if name_node else "<anonymous>",
            file_path    = file_path,
            start_line   = m_node.start_point[0],
            end_line     = m_node.end_point[0],
            parameters   = params,
            return_type  = _text(src, ret_node) if ret_node else None,
            is_method    = True,
            parent_class = class_name,
            calls        = _calls(src, m_node),
            complexity   = _complexity(m_node),
            body         = _lines_of(src_str, m_node),
        )

    walk(root)
    meta.total_functions = len(meta.functions)
    meta.total_classes   = len(meta.classes)
    return meta


# ── Go ─────────────────────────────────────────────────────────────────────────

def _extract_go(src_str: str, file_path: str) -> ASTMetadata:
    from tree_sitter import Parser
    meta = ASTMetadata(file_path=file_path, language="go")
    if "go" not in _langs():
        meta.parse_errors.append("tree-sitter Go unavailable")
        return meta

    src = src_str.encode("utf-8", errors="replace")
    parser = Parser(_langs()["go"])
    tree = parser.parse(src)
    root = tree.root_node

    def go_params(param_list) -> list[ParameterInfo]:
        if not param_list:
            return []
        out: list[ParameterInfo] = []
        for child in param_list.children:
            if child.type == "parameter_declaration":
                names = [_text(src, c) for c in child.children if c.type == "identifier"]
                ptype = next((_text(src, c) for c in child.children
                              if c.type not in ("identifier", ",", "...")), None)
                for n in names:
                    out.append(ParameterInfo(name=n, type_hint=ptype))
        return out

    for node in root.children:
        t = node.type

        if t == "import_declaration":
            for child in node.children:
                if child.type == "import_spec_list":
                    for spec in child.children:
                        if spec.type == "import_spec":
                            path = next((_text(src, c) for c in spec.children
                                         if c.type == "interpreted_string_literal"), "")
                            meta.imports.append(ImportInfo(module=path.strip('"'), line=spec.start_point[0]))
                elif child.type == "import_spec":
                    path = next((_text(src, c) for c in child.children
                                  if c.type == "interpreted_string_literal"), "")
                    meta.imports.append(ImportInfo(module=path.strip('"'), line=node.start_point[0]))

        elif t == "function_declaration":
            name_node   = node.child_by_field_name("name")
            params_node = node.child_by_field_name("parameters")
            result_node = node.child_by_field_name("result")
            meta.functions.append(FunctionInfo(
                name       = _text(src, name_node) if name_node else "<anonymous>",
                file_path  = file_path,
                start_line = node.start_point[0],
                end_line   = node.end_point[0],
                parameters = go_params(params_node),
                return_type= _text(src, result_node) if result_node else None,
                calls      = _calls(src, node),
                complexity = _complexity(node),
                body       = _lines_of(src_str, node),
            ))

        elif t == "method_declaration":
            receiver   = node.child_by_field_name("receiver")
            name_node  = node.child_by_field_name("name")
            params_node= node.child_by_field_name("parameters")
            result_node= node.child_by_field_name("result")
            parent = ""
            if receiver:
                for c in receiver.children:
                    if c.type == "parameter_declaration":
                        for sub in c.children:
                            if sub.type in ("type_identifier", "pointer_type"):
                                parent = _text(src, sub).lstrip("*")
            meta.functions.append(FunctionInfo(
                name         = _text(src, name_node) if name_node else "<anonymous>",
                file_path    = file_path,
                start_line   = node.start_point[0],
                end_line     = node.end_point[0],
                parameters   = go_params(params_node),
                return_type  = _text(src, result_node) if result_node else None,
                is_method    = True,
                parent_class = parent,
                calls        = _calls(src, node),
                complexity   = _complexity(node),
                body         = _lines_of(src_str, node),
            ))

        elif t == "type_declaration":
            for spec in node.children:
                if spec.type == "type_spec":
                    name_node  = spec.child_by_field_name("name")
                    type_node  = spec.child_by_field_name("type")
                    if type_node and type_node.type == "struct_type":
                        fields: list[str] = []
                        for c in type_node.children:
                            if c.type == "field_declaration_list":
                                for fd in c.children:
                                    if fd.type == "field_declaration":
                                        fname = next((_text(src, x) for x in fd.children
                                                      if x.type == "field_identifier"), "")
                                        if fname:
                                            fields.append(fname)
                        meta.classes.append(ClassInfo(
                            name       = _text(src, name_node) if name_node else "<anonymous>",
                            file_path  = file_path,
                            start_line = spec.start_point[0],
                            end_line   = spec.end_point[0],
                            fields     = fields,
                            body       = _lines_of(src_str, spec),
                        ))

    meta.total_functions = len(meta.functions)
    meta.total_classes   = len(meta.classes)
    return meta


# ── Public entry point ─────────────────────────────────────────────────────────

_EXTRACTORS = {
    "python":     _extract_python,
    "javascript": lambda s, p: _extract_js_ts(s, p, "javascript"),
    "typescript": lambda s, p: _extract_js_ts(s, p, "typescript"),
    "tsx":        lambda s, p: _extract_js_ts(s, p, "tsx"),
    "java":       _extract_java,
    "go":         _extract_go,
}


def extract_ast_metadata(src: str, file_path: str, language: str) -> ASTMetadata:
    """
    Parse a source file and return ASTMetadata.
    Falls back to empty metadata (no crash) for unsupported languages.
    """
    extractor = _EXTRACTORS.get(language)
    if extractor is None:
        return ASTMetadata(file_path=file_path, language=language)
    try:
        return extractor(src, file_path)
    except Exception as exc:
        logger.warning(f"AST extraction failed for {file_path} ({language}): {exc}")
        return ASTMetadata(file_path=file_path, language=language, parse_errors=[str(exc)])
