"""Configuration management for SpecForge."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Default model
DEFAULT_MODEL = os.environ.get("SPECFORGE_MODEL", "gpt-4o")

# Global model override (set by CLI --model flag)
_current_model: str = DEFAULT_MODEL


def set_model(model: str) -> None:
    """Set the model to use for all agents."""
    global _current_model
    _current_model = model


def get_model() -> str:
    """Get the current model."""
    return _current_model


def _detect_provider(model: str) -> str:
    """Detect which provider a model belongs to.

    Returns: 'anthropic', 'openrouter', 'moonshot', 'deepseek', or 'openai'.
    """
    # Anthropic native
    if model.startswith("claude") and "/" not in model:
        return "anthropic"

    # OpenRouter: any model with org/name format (e.g. moonshotai/Kimi-K2.5)
    if "/" in model:
        return "openrouter"

    # Moonshot direct API
    if model.startswith(("kimi", "moonshot")):
        return "moonshot"

    # DeepSeek
    if model.startswith("deepseek"):
        return "deepseek"

    return "openai"


# Provider configs: provider -> (env_var, base_url)
PROVIDER_CONFIG = {
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
    "moonshot": ("MOONSHOT_API_KEY", "https://api.moonshot.ai/v1"),
    "deepseek": ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1"),
}


def get_llm(temperature: float = 0.1, max_tokens: int | None = None):
    """Get a configured LLM instance based on current model.

    Supports:
    - OpenAI models (gpt-*)
    - Anthropic models (claude-*)
    - OpenRouter models (org/model format, e.g. moonshotai/Kimi-K2.5)
    - Moonshot/Kimi models (kimi-*, moonshot-*)
    - DeepSeek models (deepseek-*)
    """
    model = get_model()
    provider = _detect_provider(model)

    # Some models have temperature restrictions
    FIXED_TEMP_MODELS = {"kimi-k2.5"}
    if model in FIXED_TEMP_MODELS:
        temperature = 1.0

    kwargs = {"model": model, "temperature": temperature}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(**kwargs)

    if provider in PROVIDER_CONFIG:
        env_var, base_url = PROVIDER_CONFIG[provider]
        api_key = os.environ.get(env_var, "")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            **kwargs,
        )

    # Default: OpenAI (also supports custom base via OPENAI_API_BASE)
    from langchain_openai import ChatOpenAI
    extra = {}
    custom_base = os.environ.get("OPENAI_API_BASE")
    if custom_base:
        extra["base_url"] = custom_base
    return ChatOpenAI(**kwargs, **extra)


def validate_api_key() -> tuple[bool, str]:
    """Check that the required API key is set for the current model.

    Returns (is_valid, error_message).
    """
    model = get_model()
    provider = _detect_provider(model)

    if provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key or key.startswith("sk-ant-your"):
            return False, (
                "ANTHROPIC_API_KEY not set.\n"
                "Set it in your environment or create a .env file.\n"
                "See .env.example for details."
            )
        return True, ""

    if provider in PROVIDER_CONFIG:
        env_var, _ = PROVIDER_CONFIG[provider]
        key = os.environ.get(env_var, "")
        if not key:
            return False, (
                f"{env_var} not set.\n"
                f"Set it in your environment or create a .env file.\n"
                f"See .env.example for details."
            )
        return True, ""

    # OpenAI
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key or key.startswith("sk-your"):
        return False, (
            "OPENAI_API_KEY not set.\n"
            "Set it in your environment or create a .env file.\n"
            "See .env.example for details."
        )

    return True, ""
