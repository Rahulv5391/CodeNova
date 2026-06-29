"""
GitHub service.

Loading strategy:
  1. LangChain GithubFileLoader  — preferred; uses GitHub API, no local disk
  2. GitPython clone fallback    — used when the repo is private, large, or
                                   when the caller requests offline access

Both paths return the same interface: list[FileRecord]

LangChain loader advantages:
  - No disk I/O — loads files directly from the GitHub API
  - Built-in filtering via file_filter callable
  - Structured Document objects with rich metadata

GitPython advantages:
  - Works for private repos (token in URL)
  - Works offline / in air-gapped environments
  - Supports full git history operations needed by PR analysis
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from fastapi import HTTPException

import git
from github import Github, GithubException
from loguru import logger

from app.core.config import get_settings
from langchain_community.document_loaders import GithubFileLoader

settings = get_settings()

# ── Shared ignore rules ────────────────────────────────────────────────────────

IGNORE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".envdist",
    "build",
    ".next",
    ".nuxt",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "target",
    "vendor",
    ".idea",
    ".vscode",
    "package-lock.json",
}

IGNORE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".mp3",
    ".mov",
    ".avi",
    ".pyc",
    ".pyo",
    ".class",
    ".lock",
}

MAX_FILE_BYTES = 1_000_000  # 1 MB


# ── FileRecord — unified output type ──────────────────────────────────────────


@dataclass
class FileRecord:
    path: str  # repo-relative path, e.g. "src/auth/service.py"
    content: str  # decoded file content
    extension: str  # ".py", ".ts", ...
    size: int  # bytes
    abs_path: str = ""  # only set for GitPython-loaded files


@dataclass
class RepositoryChanges:
    latest_sha: str
    files_to_index: list[FileRecord]
    paths_to_delete: list[str]


def _should_ignore(path: str, size: int) -> bool:
    p = Path(path)
    # Any ignored directory in the path?
    if any(part in IGNORE_DIRS for part in p.parts):
        return True
    if p.suffix.lower() in IGNORE_EXTENSIONS:
        return True
    if size > MAX_FILE_BYTES:
        return True
    return False


# ── LangChain loader (primary) ─────────────────────────────────────────────────


def load_via_langchain(
    github_url: str,
    branch: str = "main",
    access_token: str | None = None,
) -> list[FileRecord]:
    """
    Use LangChain's GithubFileLoader to stream files via the GitHub API.
    Returns a list of FileRecord objects.
    Raises on auth error or if the repo is not accessible.
    """

    full_name = get_full_name(github_url)
    token = access_token or settings.github_token_for_loader

    def _file_filter(file_path: str) -> bool:
        p = Path(file_path)
        if any(part in IGNORE_DIRS for part in p.parts):
            return False
        if p.suffix.lower() in IGNORE_EXTENSIONS:
            return False
        return True

    logger.info(f"[LangChain] Loading {full_name} @ {branch} via GitHub API…")

    loader = GithubFileLoader(
        repo=full_name,
        access_token=token,
        github_api_url="https://api.github.com",
        branch=branch,
        file_filter=_file_filter,
    )

    records: list[FileRecord] = []
    try:
        docs = loader.load()
    except Exception as exc:
        logger.warning(
            f"LangChain GithubFileLoader failed: {exc} — falling back to git clone"
        )
        raise

    for doc in docs:
        content = doc.page_content
        path = doc.metadata.get("path", doc.metadata.get("source", "unknown"))
        size = len(content.encode("utf-8", errors="replace"))
        ext = Path(path).suffix.lower()

        if _should_ignore(path, size):
            continue

        records.append(
            FileRecord(
                path=path,
                content=content,
                extension=ext,
                size=size,
            )
        )

    logger.info(f"[LangChain] Loaded {len(records)} files from {full_name}")
    return records


# ── GitPython clone (fallback / offline) ──────────────────────────────────────


def _clone_path(full_name: str, branch: str) -> Path:
    safe = full_name.replace("/", "__")
    return Path(settings.repo_clone_dir) / f"{safe}__{branch}"


def _authenticated_clone_url(github_url: str, access_token: str | None = None) -> str:
    if not access_token:
        return github_url

    url = github_url.rstrip("/")
    if url.startswith("https://"):
        return url.replace(
            "https://", f"https://x-access-token:{quote(access_token)}@", 1
        )

    return github_url


def load_via_gitpython(
    github_url: str,
    branch: str = "main",
    access_token: str | None = None,
) -> tuple[list[FileRecord], str, Path]:
    """
    Clone (or pull) the repo, walk files, return (records, full_name, local_path).
    """
    url = github_url.rstrip("/").rstrip(".git")
    parts = url.split("/")
    if len(parts) < 2:
        raise ValueError(f"Cannot parse repo from URL: {github_url}")
    full_name = "/".join(parts[-2:])
    clone_to = _clone_path(full_name, branch)
    clone_to.parent.mkdir(parents=True, exist_ok=True)
    clone_url = _authenticated_clone_url(github_url, access_token)

    if clone_to.exists():
        logger.info(f"[GitPython] Pulling {full_name} @ {branch}…")
        repo = git.Repo(clone_to)
        origin = repo.remotes.origin
        original_url = next(origin.urls)
        try:
            if access_token:
                origin.set_url(clone_url)
            repo.git.fetch("origin")
            repo.git.checkout(branch)
            repo.git.pull("origin", branch)
        finally:
            if access_token:
                origin.set_url(original_url)
    else:
        logger.info(f"[GitPython] Cloning {github_url} ({branch}) → {clone_to}")
        git.Repo.clone_from(clone_url, clone_to, branch=branch, depth=1)

    records: list[FileRecord] = []
    for root, dirs, filenames in os.walk(clone_to):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for filename in filenames:
            filepath = Path(root) / filename
            ext = filepath.suffix.lower()
            try:
                size = filepath.stat().st_size
            except OSError:
                continue
            rel_path = str(filepath.relative_to(clone_to))
            if _should_ignore(rel_path, size):
                continue
            content = _read_file(str(filepath))
            if content is None:
                continue
            records.append(
                FileRecord(
                    path=rel_path,
                    content=content,
                    extension=ext,
                    size=size,
                    abs_path=str(filepath),
                )
            )

    logger.info(f"[GitPython] Loaded {len(records)} files from {full_name}")
    return records, full_name, clone_to


def _read_file(abs_path: str) -> str | None:
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as exc:
        logger.warning(f"Cannot read {abs_path}: {exc}")
        return None


# ── Smart loader: tries LangChain first, falls back to GitPython ──────────────


def load_repository(
    github_url: str,
    branch: str = "main",
    access_token: str | None = None,
    force_clone: bool = False,
) -> tuple[list[FileRecord], str, Path | None]:
    """
    Returns (records, full_name, local_path).
    local_path is None when loaded via LangChain (no disk clone).
    """

    full_name = get_full_name(github_url)

    if not force_clone:
        try:
            records = load_via_langchain(github_url, branch, access_token)
            return records, full_name, None
        except Exception as exc:
            logger.warning(f"LangChain load failed ({exc}); using git clone fallback")

    records, full_name, local_path = load_via_gitpython(
        github_url, branch, access_token
    )
    return records, full_name, local_path


# ── File tree (requires local clone) ──────────────────────────────────────────


def build_file_tree(local_path: Path) -> list[dict]:
    def _node(p: Path) -> dict:
        rel = p.relative_to(local_path)
        if p.is_dir():
            children = [
                _node(child)
                for child in sorted(p.iterdir())
                if child.name not in IGNORE_DIRS and not child.name.startswith(".")
            ]
            return {
                "name": p.name,
                "path": str(rel),
                "type": "dir",
                "children": children,
            }
        return {
            "name": p.name,
            "path": str(rel),
            "type": "file",
            "size": p.stat().st_size,
        }

    result = []
    for item in sorted(local_path.iterdir()):
        if item.name not in IGNORE_DIRS and not item.name.startswith("."):
            result.append(_node(item))
    return result


def read_file_content(abs_path: str) -> str | None:
    return _read_file(abs_path)


def delete_clone(full_name: str, branch: str) -> None:
    path = _clone_path(full_name, branch)
    if path.exists():
        shutil.rmtree(path)
        logger.info(f"Deleted clone at {path}")


# ── GitHub API helpers ─────────────────────────────────────────────────────────


def get_repo(github_url: str, access_token: str | None = None):
    try:
        name = get_full_name(github_url)
        g = Github(access_token) if access_token else Github()
        return g.get_repo(name)

    except GithubException as exc:
        raise HTTPException(
            status_code=404,
            detail="Repository not found or access denied",
        )


def get_repo_description(
    github_url: str, access_token: str | None = None
) -> str | None:
    try:
        repo = get_repo(github_url, access_token)
        return repo.description
    except GithubException as exc:
        logger.warning(f"Could not fetch repo description: {exc}")
        return None


def get_full_name(github_url: str) -> str:
    url = github_url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]

    parts = url.split("/")
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid GitHub URL")

    return "/".join(parts[-2:])


def get_latest_commit_sha(
    github_url: str,
    branch: str = "main",
    access_token: str | None = None,
) -> str | None:
    try:
        full_name = get_full_name(github_url)
        g = Github(access_token) if access_token else Github()

        repo = g.get_repo(full_name)
        branch_obj = repo.get_branch(branch)

        return branch_obj.commit.sha

    except GithubException as exc:
        logger.warning(f"Could not fetch latest commit SHA: {exc}")
        return None


def get_file_tree_from_github_api(
    github_url: str,
    branch: str = "main",
    access_token: str | None = None,
) -> list[dict]:
    """
    Returns nested file tree without cloning the repository.

    Example output:
    [
        {
            "name": "src",
            "path": "src",
            "type": "dir",
            "children": [
                {
                    "name": "main.py",
                    "path": "src/main.py",
                    "type": "file",
                }
            ],
        }
    ]
    """

    try:
        repo = get_repo(github_url, access_token)
        tree = repo.get_git_tree(branch, recursive=True)

        root: dict = {}

        for item in tree.tree:
            path = item.path

            # Skip ignored paths
            parts = path.split("/")
            if any(part in IGNORE_DIRS for part in parts):
                continue

            current = root

            for i, part in enumerate(parts):
                is_last = i == len(parts) - 1

                if is_last:
                    if item.type == "blob":
                        current.setdefault(
                            part,
                            {"name": part, "path": path, "type": "file"},
                        )
                    else:
                        current.setdefault(
                            part,
                            {"name": part, "path": path, "type": "dir", "children": {}},
                        )
                else:
                    node = current.setdefault(
                        part,
                        {
                            "name": part,
                            "path": "/".join(parts[: i + 1]),
                            "type": "dir",
                            "children": {},
                        },
                    )
                    current = node["children"]

        def normalize(nodes: dict) -> list[dict]:
            result = []

            for node in sorted(
                nodes.values(), key=lambda n: (n["type"] != "dir", n["name"].lower())
            ):
                if node["type"] == "dir":
                    node["children"] = normalize(node["children"])

                result.append(node)

            return result

        return normalize(root)

    except GithubException as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch repository tree: {exc.data}",
        )


def get_changed_files_since_commit(
    github_url: str,
    base_sha: str,
    branch: str = "main",
    access_token: str | None = None,
) -> RepositoryChanges:
    """
    Compare the indexed commit to the current branch head and return current
    file contents for added/modified/renamed files plus paths that should be
    removed from local indexes.
    """
    repo = get_repo(github_url, access_token)
    latest_sha = repo.get_branch(branch).commit.sha
    comparison = repo.compare(base_sha, latest_sha)

    files_to_index: list[FileRecord] = []
    paths_to_delete: list[str] = []

    for changed in comparison.files:
        filename = changed.filename
        previous_filename = getattr(changed, "previous_filename", None)
        status = changed.status

        if previous_filename:
            paths_to_delete.append(previous_filename)

        if status == "removed":
            paths_to_delete.append(filename)
            continue

        try:
            content_file = repo.get_contents(filename, ref=latest_sha)
        except GithubException as exc:
            logger.warning(f"Could not fetch changed file {filename}: {exc}")
            paths_to_delete.append(filename)
            continue

        if isinstance(content_file, list):
            continue

        size = content_file.size or 0
        if _should_ignore(filename, size):
            paths_to_delete.append(filename)
            continue

        try:
            content = content_file.decoded_content.decode(
                "utf-8", errors="replace"
            )
        except Exception as exc:
            logger.warning(f"Could not decode changed file {filename}: {exc}")
            continue

        files_to_index.append(
            FileRecord(
                path=filename,
                content=content,
                extension=Path(filename).suffix.lower(),
                size=size,
            )
        )

    return RepositoryChanges(
        latest_sha=latest_sha,
        files_to_index=files_to_index,
        paths_to_delete=sorted(set(paths_to_delete)),
    )


# ════════════════════════════════════════════════════════════════════════════════
# Pull Request operations
# ════════════════════════════════════════════════════════════════════════════════


@dataclass
class PRFileChange:
    filename: str
    status: str  # "added" | "modified" | "removed" | "renamed"
    additions: int
    deletions: int
    changes: int
    patch: str | None  # unified diff text (None for binary files)
    previous_filename: str | None = None  # set when status == "renamed"


@dataclass
class PRSummary:
    number: int
    title: str
    body: str
    author: str
    state: str  # "open" | "closed"
    merged: bool
    base_branch: str
    head_branch: str
    created_at: str
    updated_at: str
    url: str
    files_changed: int
    additions: int
    deletions: int
    commits: int
    mergeable: bool | None


@dataclass
class PRDetail(PRSummary):
    files: list[PRFileChange] = None  # populated only on detail fetch



def _get_repo_handle(github_url: str, access_token: str | None = None):
    full_name = get_full_name(github_url)
    g = Github(access_token) if access_token else Github()
    return g.get_repo(full_name)


def list_pull_requests(
    github_url: str,
    access_token: str | None = None,
    state: str = "open",  # "open" | "closed" | "all"
    limit: int = 30,
) -> list[PRSummary]:
    """
    List pull requests for a repository.
    Returns lightweight summaries (no file diffs — call get_pull_request for that).
    """
    repo = _get_repo_handle(github_url, access_token)
    prs = repo.get_pulls(state=state, sort="updated", direction="desc")

    results: list[PRSummary] = []
    for i, pr in enumerate(prs):
        if i >= limit:
            break
        try:
            mergeable = pr.mergeable
        except GithubException:
            mergeable = None

        results.append(
            PRSummary(
                number=pr.number,
                title=pr.title,
                body=pr.body or "",
                author=pr.user.login if pr.user else "unknown",
                state=pr.state,
                merged=pr.merged,
                base_branch=pr.base.ref,
                head_branch=pr.head.ref,
                created_at=pr.created_at.isoformat() if pr.created_at else "",
                updated_at=pr.updated_at.isoformat() if pr.updated_at else "",
                url=pr.html_url,
                files_changed=pr.changed_files,
                additions=pr.additions,
                deletions=pr.deletions,
                commits=pr.commits,
                mergeable=mergeable,
            )
        )

    logger.info(
        f"[GitHub] Listed {len(results)} {state} PRs for {get_full_name(github_url)}"
    )
    return results


def get_pull_request(
    github_url: str,
    pr_number: int,
    access_token: str | None = None,
    max_files: int = 50,
) -> PRDetail:
    """
    Fetch full PR detail including per-file diffs (unified patch text).
    """
    repo = _get_repo_handle(github_url, access_token)
    pr = repo.get_pull(pr_number)

    try:
        mergeable = pr.mergeable
    except GithubException:
        mergeable = None

    files: list[PRFileChange] = []
    for f in pr.get_files():
        if len(files) >= max_files:
            break
        files.append(
            PRFileChange(
                filename=f.filename,
                status=f.status,
                additions=f.additions,
                deletions=f.deletions,
                changes=f.changes,
                patch=getattr(f, "patch", None),  # None for binary files
                previous_filename=getattr(f, "previous_filename", None),
            )
        )

    detail = PRDetail(
        number=pr.number,
        title=pr.title,
        body=pr.body or "",
        author=pr.user.login if pr.user else "unknown",
        state=pr.state,
        merged=pr.merged,
        base_branch=pr.base.ref,
        head_branch=pr.head.ref,
        created_at=pr.created_at.isoformat() if pr.created_at else "",
        updated_at=pr.updated_at.isoformat() if pr.updated_at else "",
        url=pr.html_url,
        files_changed=pr.changed_files,
        additions=pr.additions,
        deletions=pr.deletions,
        commits=pr.commits,
        mergeable=mergeable,
        files=files,
    )

    logger.info(
        f"[GitHub] Fetched PR #{pr_number} — {len(files)} files, "
        f"+{detail.additions}/-{detail.deletions}"
    )
    return detail


def merge_pull_request(
    github_url: str,
    pr_number: int,
    access_token: str,
    commit_message: str = "",
    merge_method: str = "merge",  # "merge" | "squash" | "rebase"
) -> dict:
    """
    Merge (approve + merge) a pull request. Requires a token with write access.
    """
    repo = _get_repo_handle(github_url, access_token)
    pr = repo.get_pull(pr_number)

    if not pr.mergeable:
        raise ValueError(
            f"PR #{pr_number} is not currently mergeable (conflicts or checks pending)"
        )

    result = pr.merge(
        commit_message=commit_message or f"Merge PR #{pr_number}: {pr.title}",
        merge_method=merge_method,
    )
    logger.info(f"[GitHub] Merged PR #{pr_number}: merged={result.merged}")
    return {"merged": result.merged, "sha": result.sha, "message": result.message}


def close_pull_request(
    github_url: str,
    pr_number: int,
    access_token: str,
    comment: str = "",
) -> dict:
    """
    Close a pull request without merging (used for "reject" action).
    Optionally post a comment explaining why.
    """
    repo = _get_repo_handle(github_url, access_token)
    pr = repo.get_pull(pr_number)

    if comment:
        pr.create_issue_comment(comment)

    pr.edit(state="closed")
    logger.info(f"[GitHub] Closed PR #{pr_number}")
    return {"closed": True, "state": pr.state}


def post_pr_review_comment(
    github_url: str,
    pr_number: int,
    access_token: str,
    body: str,
    event: str = "COMMENT",  # "APPROVE" | "REQUEST_CHANGES" | "COMMENT"
) -> dict:
    """
    Post a formal PR review (shows up in GitHub's review UI, not just a comment).
    """
    repo = _get_repo_handle(github_url, access_token)
    pr = repo.get_pull(pr_number)

    review = pr.create_review(body=body, event=event)
    logger.info(f"[GitHub] Posted {event} review on PR #{pr_number}")
    return {"review_id": review.id, "state": review.state}
