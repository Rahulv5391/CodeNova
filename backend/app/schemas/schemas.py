from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal
from enum import Enum

from pydantic import BaseModel, EmailStr, HttpUrl, Field, field_validator

from app.core.llm_models import resolve_chat_model


# ── Auth ───────────────────────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    avatar_url: str | None
    role: str
    created_at: datetime
    github_id: str | None

    model_config = {"from_attributes": True}


# ── Repository ─────────────────────────────────────────────────────────────────


class RepoIngestRequest(BaseModel):
    github_url: HttpUrl
    branch: str = "main"
    github_access_token: str | None = None


class RepoOut(BaseModel):
    id: uuid.UUID
    github_url: str
    full_name: str
    branch: str
    description: str | None
    status: str
    total_files: int
    total_functions: int
    total_classes: int
    indexed_chunks: int
    created_at: datetime
    updated_at: datetime
    progress: int

    model_config = {"from_attributes": True}


class RepoStatusOut(BaseModel):
    id: uuid.UUID
    status: str
    celery_task_id: str | None
    error_message: str | None
    total_files: int
    indexed_chunks: int
    progress: int
    model_config = {"from_attributes": True}


class FileTreeNode(BaseModel):
    name: str
    path: str
    type: Literal["file", "dir"]
    size: int | None = None
    children: list[FileTreeNode] | None = None

    model_config = {"from_attributes": True}


class RepoIngestResponse(BaseModel):
    repo: RepoOut
    tree: list[FileTreeNode]


class FileOut(BaseModel):
    id: uuid.UUID
    path: str
    language: str | None
    file_size: int

    model_config = {"from_attributes": True}


class FileContentOut(BaseModel):
    path: str
    content: str
    language: str | None


class RepoMetricsOut(BaseModel):
    total_files: int
    total_functions: int
    total_classes: int
    total_chunks: int
    languages: dict[str, int]


# ── Chat ───────────────────────────────────────────────────────────────────────


# ── Chat — request bodies ──────────────────────────────────────────────────────

class ChatSessionCreate(BaseModel):
    repository_id: uuid.UUID

class ChatRequest(BaseModel):
    """Body for POST .../messages  (sync) and POST .../stream (SSE)."""
    question: str = Field(..., min_length=1, max_length=4000)
    model: str | None = Field(
        default=None,
        description="Optional OpenRouter model slug. Defaults to CHAT_MODEL from settings.",
    )
    # Optional overrides — frontend can leave these unset
    top_k: int = Field(default=8, ge=1, le=20,
                       description="Number of code chunks to retrieve from Qdrant")
    language_filter: str | None = Field(
        default=None,
        description="Only search chunks of this language, e.g. 'python'")
    include_graph: bool = Field(
        default=True,
        description="Whether to enrich context with Neo4j relationships")

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return resolve_chat_model(value)


class ChatModelOption(BaseModel):
    id: str
    label: str


class ChatModelsResponse(BaseModel):
    default_model: str
    models: list[ChatModelOption]


class SlashCommandOut(BaseModel):
    """Slash command catalogue entry for the chat UI."""
    name: str
    command: str
    title: str
    description: str
    usage: str
    requires_query: bool


class ChatHistory(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class RepoChatBootstrap(BaseModel):
    session_id: uuid.UUID
    session_title: str
    messages: list[ChatHistory]

class RepoPageResponse(BaseModel):
    repo: RepoOut
    tree: list[FileTreeNode]
    chat: RepoChatBootstrap | None = None

class DeleteMessagesRequest(BaseModel):
    # message_id: list[uuid.UUID]
    message_ids: list[str]

# ── Chat — source citation ─────────────────────────────────────────────────────

class SourceCitation(BaseModel):
    """A single code chunk cited as evidence for the answer."""
    file_path: str
    language: str | None
    symbol_type: str | None      # function | method | class | code
    symbol_name: str | None
    parent_class: str | None
    start_line: int | None
    end_line: int | None
    relevance_score: float       # cosine similarity 0–1
    snippet: str                 # first 200 chars of raw_body — for UI preview


# ── Chat — graph relationship context ─────────────────────────────────────────

class GraphRelation(BaseModel):
    kind: str       # "caller" | "dependency" | "hierarchy" | "sibling_method"
    label: str      # human-readable, e.g. "Called by UserController.create()"
    file_path: str | None = None
    symbol: str | None = None


class EvaluationMetrics(BaseModel):
    """Lightweight RAG evaluation metrics returned with each assistant answer."""
    latency_ms: int
    retrieval_latency_ms: int | None = None
    llm_latency_ms: int | None = None
    retrieved_chunks: int
    top_relevance_score: float
    avg_relevance_score: float
    recall_at_5: float | None = None
    groundedness_score: float
    hallucination_score: float
    bertscore_f1: float | None = None


# ── Chat — message objects ─────────────────────────────────────────────────────

class ChatMessageOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str                           # "user" | "assistant"
    content: str                        # full markdown text
    sources: list[SourceCitation]       # citations (empty for user msgs)
    graph_relations: list[GraphRelation] # graph context used (empty for user msgs)
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Chat — sync response ───────────────────────────────────────────────────────

class ChatResponse(BaseModel):
    """
    Returned by POST .../messages (non-streaming).

    Frontend rendering guide
    ─────────────────────────
    • `message.content`         → render as Markdown (use react-markdown / MDX)
    • `message.sources`         → render as collapsible "Sources" panel below answer
      - group by file_path for a cleaner UI
      - use snippet for hover preview
      - use start_line to deep-link into the file explorer
    • `message.graph_relations` → render as "Relationships" chip list
    • `usage`                   → optional token counter in the footer
    """
    session_id: uuid.UUID
    session_title: str
    message: ChatMessageOut
    model: str
    # LLM token usage — present when available
    usage: dict[str, int] | None = None
    metrics: EvaluationMetrics | None = None


# ── Chat — SSE stream event shapes ────────────────────────────────────────────
#
# The stream endpoint (POST .../stream) emits a sequence of newline-delimited
# JSON events. Each line is:
#     data: <JSON>\n\n
#
# Frontend should use EventSource or fetch + ReadableStream and parse each
# `data:` line as one of these discriminated union types:
#
#   { "type": "start",     "session_id": "...", "message_id": "..." }
#   { "type": "delta",     "text": "..." }          ← append to displayed text
#   { "type": "sources",   "data": [ SourceCitation, ... ] }
#   { "type": "relations", "data": [ GraphRelation,  ... ] }
#   { "type": "usage",     "data": { "prompt_tokens": N, "completion_tokens": N } }
#   { "type": "message_ids", "user_message_id": "...", "assistant_message_id": "..." }
#   { "type": "done" }
#   { "type": "error",     "message": "..." }       ← show inline error
#
# Example React hook:
#
#   const es = new EventSource(`/api/v1/chat/sessions/${id}/stream?token=${jwt}`)
#   es.onmessage = (e) => {
#     const ev = JSON.parse(e.data)
#     if (ev.type === 'delta')     setAnswer(a => a + ev.text)
#     if (ev.type === 'sources')   setSources(ev.data)
#     if (ev.type === 'relations') setRelations(ev.data)
#     if (ev.type === 'done')      es.close()
#   }

class SSEStartEvent(BaseModel):
    type: Literal["start"] = "start"
    session_id: str
    message_id: str

class SSEDeltaEvent(BaseModel):
    type: Literal["delta"] = "delta"
    text: str

class SSESourcesEvent(BaseModel):
    type: Literal["sources"] = "sources"
    data: list[SourceCitation]

class SSERelationsEvent(BaseModel):
    type: Literal["relations"] = "relations"
    data: list[GraphRelation]

class SSEUsageEvent(BaseModel):
    type: Literal["usage"] = "usage"
    data: dict[str, int]

class SSEMetricsEvent(BaseModel):
    type: Literal["metrics"] = "metrics"
    data: EvaluationMetrics

class SSEMessageIdsEvent(BaseModel):
    type: Literal["message_ids"] = "message_ids"
    user_message_id: str
    assistant_message_id: str

class SSEDoneEvent(BaseModel):
    type: Literal["done"] = "done"

class SSEErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


# ── Chat — session list / detail ──────────────────────────────────────────────

class ChatSessionOut(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    title: str | None
    created_at: datetime
    model_config = {"from_attributes": True}

class ChatSessionDetail(BaseModel):
    session: ChatSessionOut
    messages: list[ChatMessageOut]
    repo_full_name: str


# ── Documentation generation ───────────────────────────────────────────────────

class TopicInfo(BaseModel):
    """Catalogue entry — returned by GET /docs/topics."""
    id: str
    title: str
    description: str


class DocGenerateRequest(BaseModel):
    """
    Request body for POST /docs/generate.

    topics
    ──────
    List of topic IDs to generate. Pass an empty list or ["all"] to generate
    all 15 built-in topics.

    Available topic IDs:
        project_overview · tech_stack · architecture · api_reference
        data_models · database_schema · authentication · dependency_graph
        configuration · error_handling · testing_strategy · deployment_guide
        performance_notes · security_notes · onboarding_guide

    user_context
    ────────────
    Optional free-text note about the project that gets prepended to every
    topic prompt — use it for domain context the code doesn't make obvious.
    Example: "This is a multi-tenant B2B SaaS for supply-chain logistics."

    format
    ──────
    "markdown" (default) — returns the assembled .md document as a string.
    "json"               — returns only the per-section JSON, no assembled doc.
    """
    topics:       list[str] = Field(
        default=[],
        description="Topic IDs to generate. Empty list = all topics.",
    )
    user_context: str = Field(
        default="",
        max_length=1000,
        description="Optional project context to improve generation quality.",
    )
    format: str = Field(
        default="markdown",
        pattern="^(markdown|json)$",
        description="Output format: 'markdown' or 'json'.",
    )
    @field_validator("format", mode="before")
    @classmethod
    def normalize_format(cls, value: str) -> str:
        return value.lower() if isinstance(value, str) else value


class DocSectionOut(BaseModel):
    """One generated section."""
    topic_id:    str
    title:       str
    content:     str          # Markdown body
    status:      str          # "done" | "skipped" | "error"
    error:       str = ""
    tokens_used: int = 0


class DocGenerateResponse(BaseModel):
    """
    Response from POST /docs/generate.

    Frontend rendering guide
    ─────────────────────────
    Markdown format (default):
      • `full_document` → one big string; feed into react-markdown or
        highlight with a Markdown renderer (e.g. MDX, remark, marked).
      • `sections` → use for a tabbed sidebar: one tab per topic.
        Each tab shows `section.content` rendered as Markdown.

    JSON format:
      • `full_document` is "" — only `sections` is populated.
      • Good for custom rendering or feeding into another pipeline.

    Status values:
      "done"    — all requested topics succeeded
      "partial" — some topics succeeded, some errored (check section.status)
      "failed"  — no topics succeeded
    """
    doc_id:           uuid.UUID
    repository_id:    uuid.UUID
    repo_full_name:   str
    topics_requested: list[str]
    sections:         list[DocSectionOut]
    full_document:    str          # assembled Markdown (empty when format=json)
    total_tokens:     int
    status:           str          # "done" | "partial" | "failed"
    generated_at:     datetime
    format:           str

class DocFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


class DocListItem(BaseModel):
    """Summary row for GET /docs — list of past generations."""
    id: uuid.UUID
    repository_id: uuid.UUID
    topics: list[str]
    status: str
    total_tokens: int
    created_at: datetime
    model_config = {"from_attributes": True}
    format: DocFormat


class DocDetailResponse(BaseModel):
    """Full doc record for GET /docs/{doc_id}."""
    id: uuid.UUID
    repository_id: uuid.UUID
    repo_full_name: str
    topics: list[str]
    user_context: str | None
    sections: list[DocSectionOut]
    full_document: str
    status: str
    total_tokens: int
    created_at: datetime
    updated_at: datetime
    format: DocFormat



# ── Pull Requests ───────────────────────────────────────────────────────────────

class PRFileOut(BaseModel):
    filename:  str
    status:    str
    additions: int
    deletions: int
    changes:   int
    patch:     str | None
    previous_filename: str | None = None


class PRSummaryOut(BaseModel):
    """Lightweight PR listing item — returned by GET /prs/{repo_id}."""
    number:        int
    title:         str
    body:          str
    author:        str
    state:         str
    merged:        bool
    base_branch:   str
    head_branch:   str
    created_at:    str
    updated_at:    str
    url:           str
    files_changed: int
    additions:     int
    deletions:     int
    commits:       int
    mergeable:     bool | None
    # populated by joining with our DB record, if an analysis exists
    analysis_status: str = "not_analyzed"
    ai_decision:      str | None = None
    confidence_score: float | None = None
    human_decision:   str = "pending"


class PRDetailOut(PRSummaryOut):
    """Full PR detail including file diffs — returned by GET /prs/{repo_id}/{pr_number}."""
    files: list[PRFileOut] = []


class ImpactFileEntry(BaseModel):
    dependent_files:       list[dict] = []
    functions_in_file:     list[str]  = []
    callers_of_functions:  list[dict] = []
    classes_in_file:       list[str]  = []
    subclasses:            list[dict] = []


class ImpactAnalysisOut(BaseModel):
    per_file:                 dict[str, ImpactFileEntry] = {}
    total_dependent_files:    int = 0
    total_affected_functions: int = 0
    breaking_change_risk:     str = "low"   # "low" | "medium" | "high"


class PRAnalyzeRequest(BaseModel):
    """Body for POST /prs/{repo_id}/{pr_number}/analyze. No fields required — all optional overrides."""
    force_reanalyze: bool = Field(
        default=False,
        description="Re-run analysis even if a cached result already exists.",
    )


class PRAnalysisOut(BaseModel):
    """
    Full AI analysis result — returned by POST .../analyze and GET .../analysis.

    Frontend rendering guide
    ─────────────────────────
    • `summary`                  → short paragraph at the top of the PR detail view
    • `code_review`               → render as Markdown in a "Code Review" tab/panel
    • `optimization_suggestions`  → render as Markdown in an "Optimize" tab/panel
    • `impact_analysis`           → render as a dependency graph or affected-files list;
                                     `breaking_change_risk` can drive a colored badge
    • `ai_decision` + `confidence_score` → show as a badge, e.g.
                                     "✅ AI recommends APPROVE (92% confidence)"
    • `risk_flags`                → render as colored chips (security=red, performance=orange, ...)
    • `decision_reason`           → shown under the decision badge
    """
    pr_number:                int
    repository_id:             uuid.UUID
    analysis_status:           str            # "not_analyzed" | "analyzing" | "done" | "failed"
    summary:                   str | None
    code_review:                str | None
    optimization_suggestions:  str | None
    impact_analysis:            ImpactAnalysisOut
    ai_decision:                str | None      # "approve" | "request_changes" | "reject"
    confidence_score:            float | None
    risk_flags:                 list[str]
    ai_decision_reason:          str | None
    total_tokens:                int
    error_message:               str | None
    human_decision:              str            # "approved" | "rejected" | "pending"
    human_decision_note:         str | None
    created_at:                  datetime | None
    updated_at:                  datetime | None


class PRDecisionRequest(BaseModel):
    """
    Body for POST /prs/{repo_id}/{pr_number}/decision.

    action
    ──────
    "approve" — posts a formal GitHub APPROVE review, and optionally merges
    "reject"  — closes the PR on GitHub, optionally with a comment

    merge_on_approve
    ─────────────────
    Only applies when action="approve". If true, merges immediately after approving.
    Requires the connected GitHub account to have write access to the repo.

    note
    ────
    Optional human-written note, posted as a PR comment and stored alongside
    the decision for audit history.
    """
    action: str = Field(..., pattern="^(approve|reject)$")
    note: str = Field(default="", max_length=2000)
    merge_on_approve: bool = Field(default=False)
    merge_method: str = Field(default="merge", pattern="^(merge|squash|rebase)$")


class PRDecisionResponse(BaseModel):
    pr_number:      int
    human_decision: str         # "approved" | "rejected"
    github_action:  dict        # raw result from the GitHub API call (merge sha, closed state, etc.)
    decided_at:     datetime
