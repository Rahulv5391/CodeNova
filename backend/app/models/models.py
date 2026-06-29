import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    github_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    github_access_token: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(String(120))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(
        Enum("user", "admin", name="user_role"), default="user"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    repositories: Mapped[list["Repository"]] = relationship(
        back_populates="indexed_by", cascade="all, delete-orphan"
    )

    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    indexed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    github_url: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)  # "org/repo"
    branch: Mapped[str] = mapped_column(
        String(120),
        default="main",
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text)
    # ingestion state
    status: Mapped[str] = mapped_column(
        Enum(
            "pending",
            "queued",
            "cloning",
            "parsing",
            "graph_building",
            "embedding",
            "ready",
            "failed",
            "updating",
            name="repo_status",
        ),
        default="pending",
    )

    indexed_commit_sha: Mapped[str | None] = mapped_column(
        String(40), nullable=True, index=True
    )


    github_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    progress: Mapped[int] = mapped_column(Integer, default=0)

    celery_task_id: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    # repo stats (populated after indexing)
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    total_functions: Mapped[int] = mapped_column(Integer, default=0)
    total_classes: Mapped[int] = mapped_column(Integer, default=0)
    indexed_chunks: Mapped[int] = mapped_column(Integer, default=0)
    tree_json: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    indexed_by: Mapped[User] = relationship(back_populates="repositories")
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "indexed_by_user_id", "github_url", "branch", name="uq_user_repo_branch"
        ),
    )



class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="chat_sessions")
    repository: Mapped[Repository] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        Enum("user", "assistant", name="message_role"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    graph_relations: Mapped[list] = mapped_column(JSON, default=list)
    intent: Mapped[str | None] = mapped_column(String(32))
    usage: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class GeneratedDoc(Base):
    """Persisted documentation generation result for a repository."""

    __tablename__ = "generated_docs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Which topics were requested
    topics: Mapped[list] = mapped_column(JSON, default=list)
    # user-supplied context hint
    user_context: Mapped[str | None] = mapped_column(Text)
    # Assembled full markdown document
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Per-topic sections as {topic_id: {title, content, status, error}}
    sections: Mapped[dict] = mapped_column(JSON, default=dict)
    # Overall generation status
    status: Mapped[str] = mapped_column(
        Enum("pending", "generating", "done", "failed", "partial", name="doc_status"),
        default="pending",
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    # Token usage across all LLM calls
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    format: Mapped[str] = mapped_column(
        Enum("markdown", "json", name="doc_format"),
        nullable=False,
        default="markdown",
    )



class PullRequestReview(Base):
    """
    Persisted AI analysis + human decision for a single GitHub PR.
    One row per (repository, pr_number) — re-analysis overwrites the previous run.
    """
    __tablename__ = "pull_request_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pr_title: Mapped[str] = mapped_column(String(500), default="")
    pr_author: Mapped[str] = mapped_column(String(120), default="")
    pr_url: Mapped[str] = mapped_column(Text, default="")
    base_branch: Mapped[str] = mapped_column(String(120), default="")
    head_branch: Mapped[str] = mapped_column(String(120), default="")
    files_changed: Mapped[int] = mapped_column(Integer, default=0)
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)

    # AI analysis state
    analysis_status: Mapped[str] = mapped_column(
        Enum("not_analyzed", "analyzing", "done", "failed", name="pr_analysis_status"),
        default="not_analyzed",
    )
    # Structured AI output
    summary: Mapped[str | None] = mapped_column(Text)               # what changed, plain English
    code_review: Mapped[str | None] = mapped_column(Text)           # detailed review markdown
    impact_analysis: Mapped[dict] = mapped_column(JSON, default=dict)   # affected files/symbols from Neo4j + LLM read
    optimization_suggestions: Mapped[str | None] = mapped_column(Text)
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)     # ["security", "breaking_change", ...]
    confidence_score: Mapped[float | None] = mapped_column()        # 0.0 - 1.0
    ai_decision: Mapped[str | None] = mapped_column(
        Enum("approve", "request_changes", "reject", name="ai_decision_enum")
    )
    ai_decision_reason: Mapped[str | None] = mapped_column(Text)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)

    # Human decision (overrides / confirms AI)
    human_decision: Mapped[str | None] = mapped_column(
        Enum("approved", "rejected", "pending", name="human_decision_enum"),
        default="pending",
    )
    human_decision_note: Mapped[str | None] = mapped_column(Text)
    human_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
