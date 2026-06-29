"""
Slash-command routing for repository chat.

The UI can show these commands as lightweight chat shortcuts. The backend keeps
them as prompt/retrieval presets on top of the existing RAG pipeline, so command
answers still return normal chat responses with citations and graph relations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommand:
    name: str
    title: str
    description: str
    usage: str
    intent: str
    prompt_instruction: str
    search_prefix: str
    top_k: int = 8
    include_graph: bool = True
    requires_query: bool = False

    @property
    def token(self) -> str:
        return f"/{self.name}"

    def to_public_dict(self) -> dict:
        return {
            "name": self.name,
            "command": self.token,
            "title": self.title,
            "description": self.description,
            "usage": self.usage,
            "requires_query": self.requires_query,
        }


COMMANDS: dict[str, SlashCommand] = {
    "explain": SlashCommand(
        name="explain",
        title="Explain",
        description="Explain a file, symbol, flow, or concept in the repository.",
        usage="/explain AuthService.login",
        intent="explain",
        top_k=8,
        prompt_instruction=(
            "Answer as an explanation. Start with the purpose, then describe the "
            "main steps, important collaborators, inputs/outputs, and edge cases. "
            "Keep it practical and cite the files or symbols used as evidence."
        ),
        search_prefix="explain purpose behavior implementation",
    ),
    "search": SlashCommand(
        name="search",
        title="Search",
        description="Find the most relevant files and symbols for a query.",
        usage="/search jwt token validation",
        intent="locate",
        top_k=12,
        include_graph=False,
        prompt_instruction=(
            "Answer as a code search result. Rank the most relevant matches, explain "
            "why each match matters, and include file paths, symbols, and line ranges "
            "where available. Do not provide a long tutorial unless asked."
        ),
        search_prefix="find locate file symbol implementation",
        requires_query=True,
    ),
    "review": SlashCommand(
        name="review",
        title="Review",
        description="Review an area of the codebase for bugs, risks, and missing tests.",
        usage="/review authentication flow",
        intent="review",
        top_k=12,
        prompt_instruction=(
            "Answer as a senior code review. Lead with concrete findings ordered by "
            "severity. For each finding, include the affected file or symbol, why it "
            "matters, and a suggested fix. If no serious issue is visible in the "
            "retrieved context, say that clearly and list residual test gaps."
        ),
        search_prefix="review bugs security performance maintainability tests",
    ),
    "impact": SlashCommand(
        name="impact",
        title="Impact",
        description="Analyze what might be affected by changing a file or symbol.",
        usage="/impact ChatMessage model",
        intent="impact",
        top_k=10,
        prompt_instruction=(
            "Answer as an impact analysis. Identify direct dependencies, callers, "
            "importers, related schemas/routes/tests, likely breakage points, and a "
            "safe change checklist. Use graph relationships whenever available."
        ),
        search_prefix="impact dependencies callers imports affected files change risk",
    ),
    "trace": SlashCommand(
        name="trace",
        title="Trace",
        description="Trace an execution path through routes, services, and data stores.",
        usage="/trace repository ingestion",
        intent="trace",
        top_k=10,
        prompt_instruction=(
            "Answer as an execution trace. Number the path from entry point to final "
            "side effect. Mention branches, async/background work, database/vector/"
            "graph-store interactions, and where errors are handled."
        ),
        search_prefix="trace flow lifecycle route service pipeline calls",
    ),
}


@dataclass(frozen=True)
class SlashCommandInvocation:
    command: SlashCommand
    query: str
    original_text: str

    @property
    def effective_question(self) -> str:
        if self.query:
            return f"{self.command.search_prefix}: {self.query}"
        return self.command.search_prefix


def get_slash_command_catalog() -> list[dict]:
    """Return commands in the order the UI should display them."""
    return [command.to_public_dict() for command in COMMANDS.values()]


def parse_slash_command(text: str) -> SlashCommandInvocation | None:
    """Parse a leading slash command. Returns None for normal chat messages."""
    stripped = text.strip()
    match = re.match(r"^/([a-zA-Z][\w-]*)(?:\s+([\s\S]*))?$", stripped)
    if not match:
        return None

    name = match.group(1).lower()
    command = COMMANDS.get(name)
    if not command:
        return None

    query = (match.group(2) or "").strip()
    return SlashCommandInvocation(
        command=command,
        query=query,
        original_text=text,
    )


def unknown_slash_command(text: str) -> str | None:
    """Return the unknown slash token when text starts with an unsupported command."""
    stripped = text.strip()
    match = re.match(r"^/([a-zA-Z][\w-]*)(?:\s|$)", stripped)
    if not match:
        return None

    name = match.group(1).lower()
    if name in COMMANDS:
        return None
    return f"/{name}"
