"""
Neo4j knowledge graph.

Node labels   : Repo, File, Function, Class, Module
Relationships :
  (Repo)-[:HAS_FILE]->(File)
  (File)-[:CONTAINS]->(Function|Class)
  (Class)-[:HAS_METHOD]->(Function)
  (Function)-[:CALLS]->(Function)          ← best-effort, name-matched
  (Class)-[:EXTENDS]->(Class)              ← inheritance
  (File)-[:IMPORTS]->(Module)

All nodes carry repo_id so all queries can be scoped per-repo.
"""

from __future__ import annotations
import json

from loguru import logger
from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import get_settings
from app.services.ast_extractor import ASTMetadata

settings = get_settings()
_driver: AsyncDriver | None = None


def get_driver() -> AsyncDriver:
    _driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    return _driver


async def close_driver() -> None:
    global _driver
    if _driver:
        await _driver.close()
        _driver = None


async def create_indexes() -> None:
    queries = [
        "CREATE INDEX repo_id_idx      IF NOT EXISTS FOR (r:Repo)     ON (r.repo_id)",
        "CREATE INDEX file_path_idx    IF NOT EXISTS FOR (f:File)     ON (f.path, f.repo_id)",
        "CREATE INDEX func_name_idx    IF NOT EXISTS FOR (f:Function) ON (f.name, f.repo_id)",
        "CREATE INDEX class_name_idx   IF NOT EXISTS FOR (c:Class)    ON (c.name, c.repo_id)",
        "CREATE INDEX module_name_idx  IF NOT EXISTS FOR (m:Module)   ON (m.name, m.repo_id)",
    ]
    async with get_driver().session() as session:
        for q in queries:
            await session.run(q)
    logger.info("Neo4j indexes ensured")


# ── Batch writer from ASTMetadata ──────────────────────────────────────────────


async def write_ast_metadata(repo_id: str, meta: ASTMetadata) -> None:
    """
    Write all symbols from one file's ASTMetadata into Neo4j in a single
    transaction. Called once per file during ingestion.
    """
    async with get_driver().session() as session:
        tx = await session.begin_transaction()

        # ── File node ────────────────────────────────────────────────────
        await tx.run(
            """
            MERGE (f:File {path: $path, repo_id: $repo_id})
            SET f.language = $language,
                f.total_functions = $tf,
                f.total_classes   = $tc
            """,
            path=meta.file_path,
            repo_id=repo_id,
            language=meta.language,
            tf=meta.total_functions,
            tc=meta.total_classes,
        )

        # ── Import → Module edges ────────────────────────────────────────
        for imp in meta.imports:
            await tx.run(
                """
                MATCH (f:File {path: $path, repo_id: $repo_id})
                MERGE (m:Module {name: $module, repo_id: $repo_id})
                MERGE (f)-[:IMPORTS]->(m)
                """,
                path=meta.file_path,
                repo_id=repo_id,
                module=imp.module,
            )

        # ── Class nodes ──────────────────────────────────────────────────
        for cls in meta.classes:
            await tx.run(
                """
                MATCH (f:File {path: $path, repo_id: $repo_id})
                MERGE (c:Class {name: $name, repo_id: $repo_id, file_path: $path})
                SET c.start_line   = $start_line,
                    c.end_line     = $end_line,
                    c.base_classes = $base_classes,
                    c.fields       = $fields,
                    c.docstring    = $docstring,
                    c.language     = $language
                MERGE (f)-[:CONTAINS]->(c)
                """,
                path=meta.file_path,
                repo_id=repo_id,
                name=cls.name,
                start_line=cls.start_line,
                end_line=cls.end_line,
                base_classes=cls.base_classes,
                fields=cls.fields,
                docstring=cls.docstring or "",
                language=meta.language,
            )
            # EXTENDS edges (best-effort — target class may not exist yet)
            for base in cls.base_classes:
                await tx.run(
                    """
                    MERGE (sub:Class {name: $subname, repo_id: $repo_id})
                    MERGE (sup:Class {name: $supname, repo_id: $repo_id})
                    MERGE (sub)-[:EXTENDS]->(sup)
                    """,
                    subname=cls.name,
                    supname=base,
                    repo_id=repo_id,
                )

        # ── Function / Method nodes ──────────────────────────────────────
        for fn in meta.functions:
            params_json = [
                {"name": p.name, "type": p.type_hint or ""} for p in fn.parameters
            ]

            print("PARAMS =", params_json)
            print("FN =", fn.name)

            params = {
                "path": meta.file_path,
                "repo_id": repo_id,
                "name": fn.name,
                "start_line": fn.start_line,
                "end_line": fn.end_line,
                "return_type": fn.return_type or "",
                "is_async": fn.is_async,
                "is_method": fn.is_method,
                "complexity": fn.complexity,
                "docstring": fn.docstring or "",
                "parameters": params_json,
                "decorators": fn.decorators,
                "parent_class": fn.parent_class or "",
                "language": meta.language,
            }

            print(params.keys())

            await tx.run(
                """
                MATCH (f:File {path: $path, repo_id: $repo_id})
                MERGE (fn:Function {
                    name:      $name,
                    repo_id:   $repo_id,
                    file_path: $path,
                    is_method: $is_method
                })
                SET fn.start_line   = $start_line,
                    fn.end_line     = $end_line,
                    fn.return_type  = $return_type,
                    fn.is_async     = $is_async,
                    fn.complexity   = $complexity,
                    fn.docstring    = $docstring,
                    fn.parameters   = $params_json,
                    fn.decorators   = $decorators,
                    fn.parent_class = $parent_class,
                    fn.language     = $language
                MERGE (f)-[:CONTAINS]->(fn)
                """,
                path=meta.file_path,
                repo_id=repo_id,
                name=fn.name,
                start_line=fn.start_line,
                end_line=fn.end_line,
                return_type=fn.return_type or "",
                is_async=fn.is_async,
                is_method=fn.is_method,
                complexity=fn.complexity,
                docstring=fn.docstring or "",
                params_json=json.dumps(params_json),
                decorators=fn.decorators,
                parent_class=fn.parent_class or "",
                language=meta.language,
            )

            # Class-[:HAS_METHOD]->Function edge
            if fn.is_method and fn.parent_class:
                await tx.run(
                    """
                    MERGE (c:Class {name: $cls, repo_id: $repo_id})
                    MERGE (fn:Function {name: $fn, repo_id: $repo_id, file_path: $path})
                    MERGE (c)-[:HAS_METHOD]->(fn)
                    """,
                    cls=fn.parent_class,
                    fn=fn.name,
                    repo_id=repo_id,
                    path=meta.file_path,
                )

            # CALLS edges (best-effort — call target may live in other file)
            for callee in fn.calls:
                await tx.run(
                    """
                    MERGE (caller:Function {name: $caller, repo_id: $repo_id})
                    MERGE (callee:Function {name: $callee, repo_id: $repo_id})
                    MERGE (caller)-[:CALLS]->(callee)
                    """,
                    caller=fn.name,
                    callee=callee,
                    repo_id=repo_id,
                )

        await tx.commit()

    logger.debug(
        f"Neo4j: wrote {meta.total_functions} fns + {meta.total_classes} classes for {meta.file_path}"
    )


# ── Query helpers ──────────────────────────────────────────────────────────────


async def get_file_dependencies(repo_id: str, file_path: str) -> list[dict]:
    async with get_driver().session() as session:
        result = await session.run(
            "MATCH (f:File {path: $fp, repo_id: $rid})-[:IMPORTS]->(m:Module) RETURN m.name AS module",
            fp=file_path,
            rid=repo_id,
        )
        return [{"module": r["module"]} async for r in result]


async def get_callers(repo_id: str, function_name: str) -> list[dict]:
    """Which functions call function_name?"""
    async with get_driver().session() as session:
        result = await session.run(
            """
            MATCH (caller:Function {repo_id: $rid})-[:CALLS]->(callee:Function {name: $name, repo_id: $rid})
            RETURN caller.name AS caller, caller.file_path AS file_path
            """,
            rid=repo_id,
            name=function_name,
        )
        return [
            {"caller": r["caller"], "file_path": r["file_path"]} async for r in result
        ]


async def get_class_hierarchy(repo_id: str, class_name: str) -> list[dict]:
    """Return full inheritance chain for a class."""
    async with get_driver().session() as session:
        result = await session.run(
            """
            MATCH path = (c:Class {name: $name, repo_id: $rid})-[:EXTENDS*1..5]->(base:Class)
            RETURN [n IN nodes(path) | n.name] AS chain
            """,
            name=class_name,
            rid=repo_id,
        )
        rows = [r async for r in result]
        return rows[0]["chain"] if rows else []


async def get_repo_graph_summary(repo_id: str) -> dict:
    """High-level counts for the knowledge graph."""
    async with get_driver().session() as session:
        counts = {}
        for label in ("File", "Function", "Class", "Module"):
            r = await session.run(
                f"MATCH (n:{label} {{repo_id: $rid}}) RETURN count(n) AS cnt",
                rid=repo_id,
            )
            record = await r.single()
            counts[label.lower() + "s"] = record["cnt"] if record else 0

        edges = await session.run(
            """
            MATCH (a {repo_id: $rid})-[r]->(b {repo_id: $rid})
            RETURN type(r) AS rel, count(r) AS cnt
            """,
            rid=repo_id,
        )
        counts["relationships"] = {r["rel"]: r["cnt"] async for r in edges}
        return counts


async def delete_repo_graph(repo_id: str) -> None:
    async with get_driver().session() as session:
        await session.run(
            "MATCH (n {repo_id: $rid}) DETACH DELETE n",
            rid=repo_id,
        )
    logger.info(f"Deleted Neo4j graph for repo {repo_id}")


async def delete_file_graph(repo_id: str, file_paths: list[str]) -> None:
    if not file_paths:
        return

    async with get_driver().session() as session:
        await session.run(
            """
            UNWIND $paths AS path
            OPTIONAL MATCH (f:File {path: path, repo_id: $rid})
            OPTIONAL MATCH (f)-[:CONTAINS]->(symbol)
            DETACH DELETE f, symbol
            """,
            rid=repo_id,
            paths=file_paths,
        )
    logger.info(f"Deleted Neo4j graph data for {len(file_paths)} files in repo {repo_id}")


async def get_file_impact(repo_id: str, file_path: str) -> dict:
    """
    For PR impact analysis: find everything that depends on a given file.

    Returns:
      {
        "dependent_files":     [{"file_path": "...", "via": "imports"}],
        "functions_in_file":   ["funcA", "funcB"],
        "callers_of_functions": [{"function": "funcA", "caller": "...", "caller_file": "..."}],
        "classes_in_file":     ["ClassA"],
        "subclasses":          [{"class": "ClassA", "subclass": "..."}],
      }
    """
    async with get_driver().session() as session:
        # Files that import this file's module name (best-effort: match by filename stem)
        module_guess = file_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]

        dep_result = await session.run(
            """
            MATCH (dependent:File {repo_id: $rid})-[:IMPORTS]->(m:Module {repo_id: $rid})
            WHERE m.name CONTAINS $module_guess
            RETURN DISTINCT dependent.path AS file_path
            LIMIT 25
            """,
            rid=repo_id, module_guess=module_guess,
        )
        dependent_files = []
        async for r in dep_result:
            dependent_files.append({"file_path": r["file_path"], "via": "imports"})

        # Functions defined in this file
        fn_result = await session.run(
            """
            MATCH (f:File {path: $path, repo_id: $rid})-[:CONTAINS]->(fn:Function)
            RETURN fn.name AS name
            """,
            path=file_path, rid=repo_id,
        )
        functions_in_file = []
        async for r in fn_result:
            functions_in_file.append(r["name"])

        # Callers of those functions (cross-file impact)
        callers: list[dict] = []
        if functions_in_file:
            caller_result = await session.run(
                """
                UNWIND $names AS fname
                MATCH (caller:Function {repo_id: $rid})-[:CALLS]->(callee:Function {name: fname, repo_id: $rid})
                RETURN fname AS function, caller.name AS caller, caller.file_path AS caller_file
                LIMIT 40
                """,
                names=functions_in_file, rid=repo_id,
            )
            async for r in caller_result:
                callers.append({
                    "function":    r["function"],
                    "caller":      r["caller"],
                    "caller_file": r["caller_file"],
                })

        # Classes defined in this file
        cls_result = await session.run(
            """
            MATCH (f:File {path: $path, repo_id: $rid})-[:CONTAINS]->(c:Class)
            RETURN c.name AS name
            """,
            path=file_path, rid=repo_id,
        )
        classes_in_file = []
        async for r in cls_result:
            classes_in_file.append(r["name"])

        # Subclasses of those classes (breaking change risk)
        subclasses: list[dict] = []
        if classes_in_file:
            sub_result = await session.run(
                """
                UNWIND $names AS cname
                MATCH (sub:Class {repo_id: $rid})-[:EXTENDS]->(sup:Class {name: cname, repo_id: $rid})
                RETURN cname AS class, sub.name AS subclass
                LIMIT 20
                """,
                names=classes_in_file, rid=repo_id,
            )
            async for r in sub_result:
                subclasses.append({"class": r["class"], "subclass": r["subclass"]})

        return {
            "dependent_files":      dependent_files,
            "functions_in_file":    functions_in_file,
            "callers_of_functions": callers,
            "classes_in_file":      classes_in_file,
            "subclasses":           subclasses,
        }
