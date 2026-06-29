from __future__ import annotations

from app.core.config import get_settings


PREDEFINED_CHAT_MODELS: tuple[str, ...] = (
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    "google/gemini-2.5-flash-lite",
    "anthropic/claude-sonnet-4",
    "openai/gpt-4.1",
    "openai/o4-mini",
    "deepseek/deepseek-chat-v3-0324",
)


def allowed_chat_models() -> tuple[str, ...]:
    settings = get_settings()
    models = [
        settings.chat_model,
        settings.chat_model_fallback,
        *PREDEFINED_CHAT_MODELS,
    ]
    return tuple(dict.fromkeys(model for model in models if model))


def resolve_chat_model(model: str | None) -> str:
    selected = (model or "").strip() or get_settings().chat_model
    if selected not in allowed_chat_models():
        allowed = ", ".join(allowed_chat_models())
        raise ValueError(
            f"Unsupported chat model '{selected}'. Allowed models: {allowed}"
        )
    return selected
