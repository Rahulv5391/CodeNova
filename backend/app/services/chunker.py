"""
Chunker — Stage 2 of the ingestion pipeline.

Receives ASTMetadata from ast_extractor and produces symbol-aligned CodeChunks.
Each chunk is a meaningful unit: a function body, a class body, or a
sliding-window fallback for files with no extractable symbols.

The chunk content is enriched with a header that gives the LLM full context:
  # File: src/auth/service.py | Language: python
  # Symbol: AuthService.login() | Type: method | Lines: 42-78
  # Params: (email: str, password: str) -> Optional[User]
  # Calls: hash_password, db.query, create_token
  # Complexity: 4

This header is included in the embedded text so semantic search can match
on symbol names, types and descriptions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.ast_extractor import ASTMetadata, ClassInfo, FunctionInfo

LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".rs": "rust",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".cs": "csharp",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".env": "dotenv",
    ".sh": "bash",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
}

CHUNK_SIZE_LINES = 60
OVERLAP_LINES   = 10


def detect_language(extension: str) -> str:
    return LANGUAGE_MAP.get(extension.lower(), "text")


@dataclass
class CodeChunk:
    file_path:    str
    language:     str
    chunk_index:  int
    content:      str          # enriched content (header + body)
    raw_body:     str          # original source lines only
    symbol_type:  str = "code" # "function" | "class" | "method" | "struct" | "code"
    symbol_name:  str | None = None
    parent_class: str | None = None
    start_line:   int = 0
    end_line:     int = 0
    metadata:     dict = field(default_factory=dict)


# ── Header builder ─────────────────────────────────────────────────────────────

def _function_header(fn: FunctionInfo, language: str) -> str:
    params_str = ", ".join(
        f"{p.name}: {p.type_hint}" if p.type_hint else p.name
        for p in fn.parameters
    )
    sig = f"{fn.name}({params_str})"
    if fn.return_type:
        sig += f" -> {fn.return_type}"
    kind = "async method" if fn.is_async and fn.is_method else \
           "async function" if fn.is_async else \
           "method" if fn.is_method else "function"

    lines = [
        f"# File: {fn.file_path} | Language: {language}",
        f"# Symbol: {fn.parent_class + '.' if fn.parent_class else ''}{sig}",
        f"# Type: {kind} | Lines: {fn.start_line + 1}-{fn.end_line + 1}",
    ]
    if fn.decorators:
        lines.append(f"# Decorators: {', '.join(fn.decorators)}")
    if fn.calls:
        lines.append(f"# Calls: {', '.join(fn.calls[:8])}")
    if fn.complexity > 1:
        lines.append(f"# Cyclomatic complexity: {fn.complexity}")
    if fn.docstring:
        lines.append(f"# Doc: {fn.docstring[:120]}")
    lines.append("")  # blank line before body
    return "\n".join(lines)


def _class_header(cls: ClassInfo, language: str) -> str:
    lines = [
        f"# File: {cls.file_path} | Language: {language}",
        f"# Symbol: {cls.name} | Type: class | Lines: {cls.start_line + 1}-{cls.end_line + 1}",
    ]
    if cls.base_classes:
        lines.append(f"# Extends: {', '.join(cls.base_classes)}")
    if cls.decorators:
        lines.append(f"# Decorators: {', '.join(cls.decorators)}")
    if cls.methods:
        lines.append(f"# Methods: {', '.join(cls.methods[:12])}")
    if cls.fields:
        lines.append(f"# Fields: {', '.join(cls.fields[:8])}")
    if cls.docstring:
        lines.append(f"# Doc: {cls.docstring[:120]}")
    lines.append("")
    return "\n".join(lines)


def _file_header(file_path: str, language: str, start_line: int, end_line: int) -> str:
    return (
        f"# File: {file_path} | Language: {language}\n"
        f"# Lines: {start_line + 1}-{end_line + 1}\n\n"
    )


# ── Symbol-aligned chunking ────────────────────────────────────────────────────

def _chunks_from_ast(meta: ASTMetadata, src_lines: list[str]) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    covered_lines: set[int] = set()

    # Functions (already includes methods extracted from class bodies)
    for fn in meta.functions:
        header  = _function_header(fn, meta.language)
        body    = fn.body
        content = header + body
        chunk   = CodeChunk(
            file_path    = meta.file_path,
            language     = meta.language,
            chunk_index  = len(chunks),
            content      = content,
            raw_body     = body,
            symbol_type  = "method" if fn.is_method else "function",
            symbol_name  = fn.name,
            parent_class = fn.parent_class,
            start_line   = fn.start_line,
            end_line     = fn.end_line,
            metadata     = {
                "parameters": [{"name": p.name, "type": p.type_hint} for p in fn.parameters],
                "return_type": fn.return_type,
                "is_async": fn.is_async,
                "complexity": fn.complexity,
                "calls": fn.calls,
                "decorators": fn.decorators,
                "docstring": fn.docstring,
            },
        )
        chunks.append(chunk)
        covered_lines.update(range(fn.start_line, fn.end_line + 1))

    # Classes — emit a class-level chunk (signature + fields, without repeating method bodies)
    for cls in meta.classes:
        header = _class_header(cls, meta.language)
        # Class chunk = header + first 30 lines of class body (overview)
        class_lines = src_lines[cls.start_line : cls.end_line + 1]
        overview = "\n".join(class_lines[:30])
        chunks.append(CodeChunk(
            file_path    = meta.file_path,
            language     = meta.language,
            chunk_index  = len(chunks),
            content      = header + overview,
            raw_body     = overview,
            symbol_type  = "struct" if not cls.methods else "class",
            symbol_name  = cls.name,
            start_line   = cls.start_line,
            end_line     = cls.end_line,
            metadata     = {
                "base_classes": cls.base_classes,
                "methods": cls.methods,
                "fields": cls.fields,
                "docstring": cls.docstring,
            },
        ))

    return chunks


# ── Sliding-window fallback ────────────────────────────────────────────────────

def _sliding_window(
    src_lines: list[str],
    file_path: str,
    language:  str,
    start_offset: int = 0,
) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    step = CHUNK_SIZE_LINES - OVERLAP_LINES

    for i in range(0, len(src_lines), step):
        block = src_lines[i : i + CHUNK_SIZE_LINES]
        body  = "\n".join(block)
        if not body.strip():
            continue
        abs_start = start_offset + i
        abs_end   = abs_start + len(block) - 1
        header    = _file_header(file_path, language, abs_start, abs_end)
        chunks.append(CodeChunk(
            file_path   = file_path,
            language    = language,
            chunk_index = len(chunks),
            content     = header + body,
            raw_body    = body,
            symbol_type = "code",
            start_line  = abs_start,
            end_line    = abs_end,
        ))
    return chunks


# ── Public API ─────────────────────────────────────────────────────────────────

def chunk_from_ast(meta: ASTMetadata, src: str) -> list[CodeChunk]:
    """
    Main entry point used by the ingestion pipeline.

    Takes the ASTMetadata (from ast_extractor) and the raw source text.
    Returns a list of CodeChunks ready for embedding.
    """
    src_lines = src.splitlines()

    # If AST produced symbols → symbol-aligned chunks
    if meta.functions or meta.classes:
        chunks = _chunks_from_ast(meta, src_lines)
        # Sliding window over file-level code not covered by any symbol
        # (module-level logic, global config, etc.)
        covered: set[int] = set()
        for c in chunks:
            covered.update(range(c.start_line, c.end_line + 1))
        uncovered = [line for i, line in enumerate(src_lines) if i not in covered]
        if len(uncovered) > 5:
            fallback = _sliding_window(uncovered, meta.file_path, meta.language)
            chunks.extend(fallback)
        # Re-index
        for i, c in enumerate(chunks):
            c.chunk_index = i
        return chunks

    # No symbols → pure sliding window (e.g. JSON, YAML, Markdown, config)
    return _sliding_window(src_lines, meta.file_path, meta.language)
