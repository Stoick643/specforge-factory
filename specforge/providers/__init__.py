"""LLM Provider abstraction for SpecForge.

Supports two modes:
- ApiProvider: Direct LLM API calls via langchain (needs API key)
- PiProvider: Pi RPC subprocess (no API key, uses user's Claude/Max plan)

Thread-safe via RunConfig: each generation run gets its own config and provider instance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class LlmProvider(Protocol):
    """Protocol for LLM providers. All agents use this interface."""

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        """Send a prompt and return the text response."""
        ...

    def invoke_structured(self, system_prompt: str, user_prompt: str, schema_class):
        """Try to get a structured response. Returns parsed object or None on failure."""
        ...

    def stop(self) -> None:
        """Clean up resources (e.g. stop subprocess)."""
        ...


class ApiProvider:
    """Provider that uses langchain ChatOpenAI/ChatAnthropic for direct API calls."""

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self._model = model
        self._api_key = api_key

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage
        llm = self._get_llm(temperature=0.1)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = llm.invoke(messages)
        return response.content

    def invoke_structured(self, system_prompt: str, user_prompt: str, schema_class):
        from langchain_core.messages import HumanMessage, SystemMessage
        llm = self._get_llm(temperature=0.2)
        try:
            structured_llm = llm.with_structured_output(schema_class)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
            return structured_llm.invoke(messages)
        except Exception:
            return None

    def _get_llm(self, temperature: float = 0.1):
        from specforge.config import get_llm
        return get_llm(
            temperature=temperature,
            api_key=self._api_key,
            model_override=self._model,
        )

    def stop(self) -> None:
        pass  # Nothing to clean up


class PiProvider:
    """Provider that uses Pi's RPC mode as a subprocess. No API key needed."""

    def __init__(self):
        from specforge.providers.pi_rpc import PiRpcClient
        self._client = PiRpcClient()
        self._started = False

    def _ensure_started(self):
        if not self._started:
            self._client.start()
            self._started = True

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        self._ensure_started()
        # Combine system + user prompt since Pi RPC is a single message interface
        combined = f"{system_prompt}\n\n---\n\n{user_prompt}"
        return self._client.prompt(combined)

    def invoke_structured(self, system_prompt: str, user_prompt: str, schema_class):
        # Pi RPC doesn't support structured output — always return None
        # Agents will fall back to manual JSON parsing
        return None

    def stop(self) -> None:
        if self._started:
            self._client.stop()
            self._started = False


@dataclass
class RunConfig:
    """Configuration for a single generation run.

    Each run gets its own RunConfig with its own provider instance.
    Thread-safe: no shared mutable state between runs.
    """
    provider_type: str = "api"  # "api" or "pi"
    model: str | None = None
    api_key: str | None = None  # Explicit API key (avoids os.environ)
    on_progress: Callable | None = None  # Per-run progress callback (for event scoping)
    _provider: LlmProvider | None = field(default=None, init=False, repr=False)

    def get_provider(self) -> LlmProvider:
        """Get or create the provider for this run."""
        if self._provider is None:
            if self.provider_type == "pi":
                self._provider = PiProvider()
            else:
                self._provider = ApiProvider(model=self.model, api_key=self.api_key)
        return self._provider

    def stop(self) -> None:
        """Clean up the provider."""
        if self._provider is not None:
            self._provider.stop()
            self._provider = None


# ── Global convenience API (for CLI / single-threaded use) ──────────

_current_config: RunConfig | None = None


def set_provider_type(provider_type: str) -> None:
    """Set which provider to use (global, for CLI)."""
    global _current_config
    _current_config = RunConfig(provider_type=provider_type)


def get_provider() -> LlmProvider:
    """Get the current LLM provider (global, for CLI).

    For thread-safe usage, use RunConfig.get_provider() instead.
    """
    global _current_config
    if _current_config is None:
        _current_config = RunConfig()
    return _current_config.get_provider()


def stop_provider() -> None:
    """Stop and clean up the current provider (global, for CLI)."""
    global _current_config
    if _current_config is not None:
        _current_config.stop()
        _current_config = None
