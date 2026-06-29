"""
Documentation Agent — generates structured technical documentation for a repository.

Design
──────
Each documentation topic is a self-contained LLM call with its own:
  • Data fetcher   — pulls exactly the right context from Qdrant + Neo4j
  • System prompt  — tuned for that topic's output format
  • Output section — titled Markdown block

All topic calls run in parallel (asyncio.gather).  Results are assembled into
a single Markdown document and also returned as individual sections so the
frontend can render them in tabs / panels.

Model: google/gemini-flash-1.5  (one tier up from chat model — docs need more
       reasoning depth and are generated once, not interactively, so cost is OK)

Topic catalogue (15 topics)
────────────────────────────
 1.  project_overview       — purpose, features, business logic
 2.  tech_stack             — languages, frameworks, libraries, infra
 3.  architecture           — component map, layers, data flow
 4.  api_reference          — all routes: method, path, params, response shapes
 5.  data_models            — classes/structs/schemas and their fields
 6.  database_schema        — ORM models, tables, relationships, indexes (if any)
 7.  authentication         — auth mechanism, token flow, RBAC
 8.  dependency_graph       — external packages and internal module coupling
 9.  configuration          — env vars, config files, feature flags
10.  error_handling         — exception hierarchy, error patterns, retry logic
11.  testing_strategy       — test types, coverage approach, mocking patterns
12.  deployment_guide       — containerisation, env setup, CI/CD, deploy steps
13.  performance_notes      — caching, async patterns, known bottlenecks
14.  security_notes         — input validation, secrets management, known risks
15.  onboarding_guide       — how to clone, run locally, first PR walkthrough
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.services.embeddings import embed_query
from app.services.graph_store import get_driver, get_repo_graph_summary
from app.services.vector_store import search_chunks

settings = get_settings()

DOC_MODEL   = "google/gemini-2.5-flash"   # stronger reasoning for long-form docs
MAX_TOKENS  = 3000                         # per topic — gives room for thoroughness
TEMPERATURE = 0.25


# ── Topic registry ─────────────────────────────────────────────────────────────

@dataclass
class TopicSpec:
    id: str
    title: str
    description: str           # shown to the user in the API catalogue
    search_queries: list[str]  # Qdrant semantic queries to pull relevant chunks
    top_k: int = 6             # chunks per query (deduped)
    needs_graph: bool = False  # whether to pull Neo4j context
    system_prompt: str = ""    # set below


ALL_TOPICS: list[TopicSpec] = [
    TopicSpec(
        id="project_overview",
        title="Project Overview",
        description="High-level purpose, core features, business logic, and target users.",
        search_queries=[
            "what does this project do",
            "main features application purpose",
            "business logic core functionality",
            "project description readme",
        ],
        top_k=6,
    ),
    TopicSpec(
        id="tech_stack",
        title="Technology Stack",
        description="All languages, frameworks, libraries, and infrastructure choices.",
        search_queries=[
            "framework library import dependency",
            "database cache queue message broker",
            "frontend backend infrastructure cloud",
            "package.json requirements.txt pyproject",
        ],
        top_k=8,
    ),
    TopicSpec(
        id="architecture",
        title="System Architecture",
        description="Component breakdown, layers, service interactions, and data flow.",
        search_queries=[
            "architecture component service layer",
            "data flow pipeline request response lifecycle",
            "module structure entry point bootstrap",
            "service integration external API",
        ],
        top_k=8,
        needs_graph=True,
    ),
    TopicSpec(
        id="api_reference",
        title="API Reference",
        description="All HTTP endpoints with methods, paths, parameters, and response shapes.",
        search_queries=[
            "router endpoint route handler GET POST PUT DELETE PATCH",
            "request body response schema API endpoint",
            "controller route path parameter query param",
            "REST API endpoint handler decorator",
        ],
        top_k=12,
    ),
    TopicSpec(
        id="data_models",
        title="Data Models & Schemas",
        description="Domain classes, Pydantic models, TypeScript interfaces, and their fields.",
        search_queries=[
            "class model schema fields attributes",
            "Pydantic BaseModel TypeScript interface type definition",
            "data class struct entity domain object",
            "validation schema serialiser deserialiser",
        ],
        top_k=10,
        needs_graph=True,
    ),
    TopicSpec(
        id="database_schema",
        title="Database Schema",
        description="ORM models, table definitions, relationships, and indexes.",
        search_queries=[
            "database table column ORM model SQLAlchemy Prisma",
            "foreign key relationship index migration",
            "schema entity relationship primary key",
            "MongoDB collection Postgres table MySQL schema",
        ],
        top_k=8,
    ),
    TopicSpec(
        id="authentication",
        title="Authentication & Authorisation",
        description="Auth mechanism, token lifecycle, session management, and RBAC.",
        search_queries=[
            "authentication login JWT token session",
            "OAuth middleware permission role access control",
            "password hash verify token refresh",
            "authorisation guard decorator permission check",
        ],
        top_k=8,
        needs_graph=True,
    ),
    TopicSpec(
        id="dependency_graph",
        title="Dependency Graph",
        description="External package dependencies and internal module coupling analysis.",
        search_queries=[
            "import require dependency external package",
            "module coupling service injection dependency",
            "third party library version package manager",
        ],
        top_k=6,
        needs_graph=True,
    ),
    TopicSpec(
        id="configuration",
        title="Configuration & Environment",
        description="Environment variables, config files, secrets, and feature flags.",
        search_queries=[
            "environment variable config settings dotenv",
            "configuration file secrets feature flag",
            "os.environ process.env config class settings",
            ".env config.yaml application properties",
        ],
        top_k=6,
    ),
    TopicSpec(
        id="error_handling",
        title="Error Handling",
        description="Exception hierarchy, error patterns, retry logic, and error responses.",
        search_queries=[
            "exception error handling try catch raise",
            "HTTP error status code error response",
            "retry backoff fallback error recovery",
            "custom exception error class handler middleware",
        ],
        top_k=6,
    ),
    TopicSpec(
        id="testing_strategy",
        title="Testing Strategy",
        description="Test types, framework choices, coverage approach, and mocking patterns.",
        search_queries=[
            "test unit integration pytest jest mocha",
            "mock stub fixture test setup teardown",
            "test coverage assertion expect describe it",
            "e2e end to end test automation",
        ],
        top_k=6,
    ),
    TopicSpec(
        id="deployment_guide",
        title="Deployment Guide",
        description="Docker setup, environment configuration, CI/CD pipeline, and deploy steps.",
        search_queries=[
            "Docker Dockerfile docker-compose container",
            "CI CD GitHub Actions deploy pipeline",
            "production deploy cloud AWS GCP Azure Vercel",
            "environment setup build run start command",
        ],
        top_k=6,
    ),
    TopicSpec(
        id="performance_notes",
        title="Performance & Caching",
        description="Caching strategies, async patterns, batching, and known bottlenecks.",
        search_queries=[
            "cache Redis caching strategy TTL",
            "async await concurrent parallel performance",
            "batch queue background job worker",
            "pagination lazy load performance optimisation",
        ],
        top_k=6,
    ),
    TopicSpec(
        id="security_notes",
        title="Security Notes",
        description="Input validation, secrets management, CORS, rate limiting, and known risks.",
        search_queries=[
            "security input validation sanitise CORS",
            "rate limit throttle secrets encryption",
            "SQL injection XSS CSRF vulnerability",
            "HTTPS TLS certificate security header",
        ],
        top_k=6,
    ),
    TopicSpec(
        id="onboarding_guide",
        title="Developer Onboarding Guide",
        description="Step-by-step: clone, install, run locally, run tests, make first contribution.",
        search_queries=[
            "install setup getting started local development",
            "clone run start development server",
            "contributing guide first PR code style lint",
            "prerequisites requirements setup guide README",
        ],
        top_k=6,
    ),
]

TOPIC_MAP: dict[str, TopicSpec] = {t.id: t for t in ALL_TOPICS}


# ── Per-topic system prompts ───────────────────────────────────────────────────

_BASE_RULES = """
Output rules
────────────
- Write in clean, professional Markdown.
- Use `## Subheadings` for major subsections.
- Use inline code for symbols: `ClassName.method()`, `ENV_VAR`, `endpoint/path`.
- Use fenced code blocks with the language tag for all code examples.
- Be thorough but do not pad. Omit sections for which there is no evidence in the context.
- If the context does not contain enough information, state that clearly — do not invent details.
- Do NOT include the section title as an H1 at the top — the caller adds it.
"""

_PROMPTS: dict[str, str] = {
    "project_overview": f"""You are a technical writer producing a Project Overview section.
Extract: what the project does, who it is for, the core features (bulleted list),
and any business domain or domain-specific logic visible in the code.
{_BASE_RULES}""",

    "tech_stack": f"""You are a technical writer producing a Technology Stack section.
List ALL languages, frameworks, libraries, databases, caches, queues, and infrastructure tools
you can identify from the imports, config files, and dependency declarations.
Organise into subsections: Languages · Backend · Frontend · Data Stores · Infrastructure · Other.
For each technology, add a one-line description of its role in this project.
{_BASE_RULES}""",

    "architecture": f"""You are a software architect producing a System Architecture section.
Describe: the overall architecture style (monolith / microservices / serverless / layered etc.),
the main components and their responsibilities, how they interact, and the request lifecycle.
Use a Markdown table for the component map. Include a textual data-flow walkthrough.
The GRAPH CONTEXT section (if present) shows module relationships — use it.
{_BASE_RULES}""",

    "api_reference": f"""You are a technical writer producing an API Reference section.
For EVERY route/endpoint you find in the context, produce a subsection with:
  - **Method and path**: e.g. `POST /api/v1/auth/login`
  - **Description**: one sentence
  - **Request body / query params**: table of name | type | required | description
  - **Response**: shape and example (inferred from schemas)
  - **Auth required**: yes/no
Group endpoints by resource (Auth, Users, Repos, etc.).
{_BASE_RULES}""",

    "data_models": f"""You are a technical writer producing a Data Models section.
For every class, interface, schema, or struct in the context:
  - Give its name and purpose
  - List its fields in a table: field | type | description
  - Note any validation rules, relationships, or constraints
  - Note base classes / interfaces it implements
Use the GRAPH CONTEXT (inheritance chains) where available.
{_BASE_RULES}""",

    "database_schema": f"""You are a database engineer producing a Database Schema section.
For every ORM model, table definition, or schema file in the context:
  - Table/collection name and purpose
  - Column table: name | type | nullable | default | description
  - Relationships (FK references, one-to-many, many-to-many)
  - Indexes and unique constraints
If no database code is found in the context, say so explicitly.
{_BASE_RULES}""",

    "authentication": f"""You are a security engineer producing an Authentication & Authorisation section.
Cover: the auth mechanism (JWT / OAuth / session / API key), the token lifecycle
(issue → validate → refresh → revoke), how roles/permissions are enforced,
and any middleware or decorators involved.
{_BASE_RULES}""",

    "dependency_graph": f"""You are a software architect producing a Dependency Graph section.
Part 1 — External dependencies: list all third-party packages/libraries with their purpose.
Part 2 — Internal coupling: from the GRAPH CONTEXT imports and call edges, identify
which modules depend on which, and highlight tightly coupled areas.
{_BASE_RULES}""",

    "configuration": f"""You are a DevOps engineer producing a Configuration & Environment section.
List ALL environment variables and config keys with:
  - Variable name
  - Purpose / what it controls
  - Example / default value (if visible)
  - Whether it is required or optional
Also describe any config files (YAML, TOML, .env, etc.) and their purpose.
{_BASE_RULES}""",

    "error_handling": f"""You are a software engineer producing an Error Handling section.
Describe: the exception / error hierarchy used, how errors are caught and transformed
into responses, retry / backoff logic, and any logging or alerting on errors.
Show the error response shape expected by clients.
{_BASE_RULES}""",

    "testing_strategy": f"""You are a QA engineer producing a Testing Strategy section.
Describe: the test framework(s) used, the types of tests present (unit / integration / e2e),
how mocking is done, any fixtures or factories, and the approach to test data.
If coverage config is visible, include it.
{_BASE_RULES}""",

    "deployment_guide": f"""You are a DevOps engineer producing a Deployment Guide.
Provide step-by-step instructions to deploy this project to production, covering:
1. Prerequisites
2. Environment setup (required env vars)
3. Docker / container build and run commands (exact shell commands)
4. CI/CD pipeline overview (if config found)
5. Health check and verification steps
{_BASE_RULES}""",

    "performance_notes": f"""You are a performance engineer producing a Performance & Caching section.
Identify and describe: caching strategies (what is cached, TTL, invalidation),
async / concurrent patterns, background job processing, pagination, and any
areas of code that appear performance-sensitive or potentially problematic.
{_BASE_RULES}""",

    "security_notes": f"""You are a security engineer producing a Security Notes section.
Cover: input validation / sanitisation, secret management approach, CORS configuration,
rate limiting, authentication security (token expiry, rotation), and any potential
security risks visible in the code (and how they are or are not mitigated).
{_BASE_RULES}""",

    "onboarding_guide": f"""You are a developer advocate producing a Developer Onboarding Guide.
Write a step-by-step guide for a new contributor to:
1. Clone and set up the project locally (exact commands)
2. Install dependencies
3. Configure environment variables
4. Run the development server
5. Run tests
6. Understand the codebase entry points
7. Make and submit their first contribution
{_BASE_RULES}""",
}

# Attach prompts to topic specs
for _spec in ALL_TOPICS:
    _spec.system_prompt = _PROMPTS.get(_spec.id, _BASE_RULES)


# ── Data fetchers ──────────────────────────────────────────────────────────────

async def _fetch_chunks_for_topic(
    spec: TopicSpec,
    repo_id: str,
) -> list[dict]:
    """Run all search_queries for a topic and deduplicate by file_path+start_line."""
    tasks = [
        embed_query(q) for q in spec.search_queries
    ]
    vectors = await asyncio.gather(*tasks)

    seen: set[str] = set()
    chunks: list[dict] = []

    search_tasks = [
        search_chunks(vec, repo_id=repo_id, top_k=spec.top_k)
        for vec in vectors
    ]
    results = await asyncio.gather(*search_tasks)

    for batch in results:
        for chunk in batch:
            key = f"{chunk['file_path']}:{chunk.get('start_line', 0)}"
            if key not in seen:
                seen.add(key)
                chunks.append(chunk)

    # Sort by relevance (highest score first), cap total
    chunks.sort(key=lambda c: c.get("score", 0), reverse=True)
    return chunks[: spec.top_k * 2]  # generous cap after dedup


async def _fetch_graph_context_for_topic(
    spec: TopicSpec,
    repo_id: str,
    chunks: list[dict],
) -> str:
    """
    Pull Neo4j context relevant to this topic.
    Returns a formatted Markdown string (empty if nothing found).
    """
    if not spec.needs_graph:
        return ""

    lines: list[str] = []

    try:
        # Repo-level graph summary
        summary = await get_repo_graph_summary(repo_id)
        lines.append(
            f"**Graph summary**: {summary.get('files', 0)} files · "
            f"{summary.get('functions', 0)} functions · "
            f"{summary.get('classes', 0)} classes · "
            f"{summary.get('modules', 0)} external modules"
        )

        # For each unique class in chunks, get full method list from Neo4j
        class_names: set[str] = set()
        for c in chunks:
            if c.get("symbol_type") == "class" and c.get("symbol_name"):
                class_names.add(c["symbol_name"])
            if c.get("parent_class"):
                class_names.add(c["parent_class"])

        if class_names:
            async with get_driver().session() as session:
                for cls_name in list(class_names)[:8]:
                    result = await session.run(
                        """
                        MATCH (c:Class {name: $name, repo_id: $rid})-[:HAS_METHOD]->(fn:Function)
                        RETURN fn.name AS method,
                               fn.return_type AS ret,
                               fn.parameters AS params,
                               fn.complexity AS complexity,
                               fn.docstring AS docstring
                        ORDER BY fn.start_line
                        """,
                        name=cls_name, rid=repo_id,
                    )
                    methods = [dict(r) async for r in result]
                    if methods:
                        lines.append(f"\n**`{cls_name}` methods:**")
                        for m in methods[:10]:
                            ret = f" → `{m['ret']}`" if m.get("ret") else ""
                            doc = f" — {m['docstring'][:60]}" if m.get("docstring") else ""
                            lines.append(f"- `{m['method']}(){ret}`{doc}")

        # Top import relationships
        async with get_driver().session() as session:
            import_result = await session.run(
                """
                MATCH (f:File {repo_id: $rid})-[:IMPORTS]->(m:Module)
                RETURN m.name AS module, count(f) AS usage
                ORDER BY usage DESC LIMIT 15
                """,
                rid=repo_id,
            )
            top_imports: list[dict] = []
            async for r in import_result:
                top_imports.append({"module": r["module"], "usage": r["usage"]})
            if top_imports:
                lines.append(
                    "\n**Most-imported modules**: "
                    + ", ".join(f"`{i['module']}` ({i['usage']}×)" for i in top_imports[:10])
                )

    except Exception as exc:
        logger.debug(f"Graph context fetch for {spec.id} failed (non-fatal): {exc}")

    return "\n".join(lines)


# ── Per-topic LLM call ─────────────────────────────────────────────────────────

def _format_chunks_for_doc(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        path  = c.get("file_path", "")
        lang  = c.get("language", "")
        stype = c.get("symbol_type", "")
        sname = c.get("symbol_name", "")
        body  = c.get("raw_body") or c.get("content", "")
        meta  = c.get("metadata", {})

        label = f"`{path}`"
        if sname:
            parent = c.get("parent_class")
            fqn    = f"{parent}.{sname}" if parent else sname
            label += f" — {stype} `{fqn}`"
        if meta.get("return_type"):
            label += f" → `{meta['return_type']}`"

        parts.append(f"**[{i}] {label}**\n```{lang}\n{body[:800]}\n```")
    return "\n\n".join(parts)


def _llm() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key  = settings.openrouter_api_key,
        base_url = settings.openrouter_base_url,
        default_headers={
            "HTTP-Referer": "https://codenavigator.dev",
            "X-Title":      "CodeNavigator",
        },
    )


@dataclass
class SectionResult:
    topic_id: str
    title: str
    content: str       # Markdown body (no H1 title — caller wraps it)
    status: str        # "done" | "skipped" | "error"
    error: str = ""
    tokens_used: int = 0


async def _generate_section(
    spec: TopicSpec,
    repo_id: str,
    repo_full_name: str,
    user_context: str,
) -> SectionResult:
    """
    Full pipeline for a single topic:
      fetch chunks → fetch graph context → build prompt → LLM call → return section
    """
    try:
        # Fetch data
        chunks       = await _fetch_chunks_for_topic(spec, repo_id)
        graph_ctx    = await _fetch_graph_context_for_topic(spec, repo_id, chunks)

        if not chunks and not graph_ctx:
            return SectionResult(
                topic_id = spec.id,
                title    = spec.title,
                content  = f"_No relevant code found for this section in `{repo_full_name}`._",
                status   = "skipped",
            )

        # Build prompt
        context_parts = [f"**Repository:** `{repo_full_name}`"]
        if user_context:
            context_parts.append(f"**Additional context from user:** {user_context}")
        if chunks:
            context_parts.append(
                f"**Retrieved code ({len(chunks)} chunks):**\n\n" + _format_chunks_for_doc(chunks)
            )
        if graph_ctx:
            context_parts.append(f"**Knowledge graph context:**\n\n{graph_ctx}")

        context   = "\n\n---\n\n".join(context_parts)
        user_msg  = (
            f"<context>\n{context}\n</context>\n\n"
            f"Generate the **{spec.title}** section for this repository's documentation."
        )

        messages = [
            {"role": "system", "content": spec.system_prompt},
            {"role": "user",   "content": user_msg},
        ]

        resp = await _llm().chat.completions.create(
            model       = DOC_MODEL,
            messages    = messages,
            max_tokens  = MAX_TOKENS,
            temperature = TEMPERATURE,
        )

        content     = resp.choices[0].message.content or ""
        tokens_used = resp.usage.total_tokens if resp.usage else 0

        return SectionResult(
            topic_id    = spec.id,
            title       = spec.title,
            content     = content.strip(),
            status      = "done",
            tokens_used = tokens_used,
        )

    except Exception as exc:
        logger.exception(f"Section generation failed for topic {spec.id}: {exc}")
        return SectionResult(
            topic_id = spec.id,
            title    = spec.title,
            content  = f"_Generation failed for this section: {exc}_",
            status   = "error",
            error    = str(exc),
        )


# ── Document assembler ─────────────────────────────────────────────────────────

_DOC_HEADER_TEMPLATE = """\
# {repo_name} — Technical Documentation

> Auto-generated by CodeNavigator on {date}
> Repository: [{repo_name}]({github_url})

---

"""


def _assemble_document(
    repo_full_name: str,
    github_url: str,
    sections: list[SectionResult],
) -> str:
    from datetime import UTC, datetime

    header = _DOC_HEADER_TEMPLATE.format(
        repo_name  = repo_full_name,
        github_url = github_url,
        date       = datetime.now(UTC).strftime("%Y-%m-%d"),
    )

    # Table of contents
    toc_lines = ["## Table of Contents\n"]
    for i, s in enumerate(sections, 1):
        anchor = s.title.lower().replace(" ", "-").replace("&", "").replace("/", "")
        anchor = "".join(c for c in anchor if c.isalnum() or c == "-")
        toc_lines.append(f"{i}. [{s.title}](#{anchor})")
    toc = "\n".join(toc_lines) + "\n\n---\n\n"

    # Section bodies
    bodies: list[str] = []
    for s in sections:
        bodies.append(f"## {s.title}\n\n{s.content}\n\n---\n")

    return header + toc + "\n".join(bodies)


# ── Public entry point ─────────────────────────────────────────────────────────

@dataclass
class DocGenResult:
    doc_id: str
    repo_id: str
    topics_requested: list[str]
    sections: dict[str, dict]      # topic_id → {title, content, status, error, tokens_used}
    full_document: str             # assembled Markdown
    total_tokens: int
    status: str                    # "done" | "partial" | "failed"


async def generate_documentation(
    repo_id: str,
    repo_full_name: str,
    github_url: str,
    topic_ids: list[str],
    user_context: str = "",
    doc_id: str | None = None,
) -> DocGenResult:
    """
    Generate documentation for the requested topics in parallel.

    topic_ids: list of topic IDs from TOPIC_MAP.
               Pass [] or ["all"] to generate all 15 topics.
    user_context: free-text hint from the user about the project,
                  e.g. "This is a B2B SaaS for logistics companies."
    """
    import uuid

    doc_id = doc_id or str(uuid.uuid4())

    # Resolve topic specs
    if not topic_ids or topic_ids == ["all"]:
        specs = ALL_TOPICS
    else:
        specs = [TOPIC_MAP[tid] for tid in topic_ids if tid in TOPIC_MAP]
        unknown = [tid for tid in topic_ids if tid not in TOPIC_MAP]
        if unknown:
            logger.warning(f"Unknown topic IDs (skipped): {unknown}")

    if not specs:
        return DocGenResult(
            doc_id           = doc_id,
            repo_id          = repo_id,
            topics_requested = topic_ids,
            sections         = {},
            full_document    = "_No valid topics requested._",
            total_tokens     = 0,
            status           = "failed",
        )

    logger.info(
        f"Generating docs for {repo_full_name} | "
        f"{len(specs)} topics | model={DOC_MODEL}"
    )

    # Run all topic generations in parallel
    tasks = [
        _generate_section(spec, repo_id, repo_full_name, user_context)
        for spec in specs
    ]
    results: list[SectionResult] = await asyncio.gather(*tasks)

    # Build sections dict
    sections: dict[str, dict] = {}
    total_tokens = 0
    has_error    = False
    has_done     = False

    for r in results:
        sections[r.topic_id] = {
            "title":       r.title,
            "content":     r.content,
            "status":      r.status,
            "error":       r.error,
            "tokens_used": r.tokens_used,
        }
        total_tokens += r.tokens_used
        if r.status == "done":
            has_done = True
        if r.status == "error":
            has_error = True

    # Assemble full document (in requested order)
    ordered_results = [r for r in results if r.status in ("done", "skipped")]
    full_document   = _assemble_document(repo_full_name, github_url, ordered_results)

    status = "done" if (has_done and not has_error) else ("partial" if has_done else "failed")

    logger.info(
        f"Doc gen complete for {repo_full_name} | "
        f"status={status} total_tokens={total_tokens}"
    )

    return DocGenResult(
        doc_id           = doc_id,
        repo_id          = repo_id,
        topics_requested = [s.id for s in specs],
        sections         = sections,
        full_document    = full_document,
        total_tokens     = total_tokens,
        status           = status,
    )
