"""LLM Provider abstraction for SpecForge.

Supports two modes:
- ApiProvider: Direct LLM API calls via langchain (needs API key)
- PiProvider: Pi RPC subprocess (no API key, uses user's Claude/Max plan)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


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

    def __init__(self):
        from specforge.config import get_llm
        self._get_llm = get_llm

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


# Global provider instance
_current_provider: LlmProvider | None = None
_provider_type: str = "api"  # "api" or "pi"


def set_provider_type(provider_type: str) -> None:
    """Set which provider to use."""
    global _provider_type, _current_provider
    _provider_type = provider_type
    _current_provider = None  # Reset so it gets recreated


def get_provider() -> LlmProvider:
    """Get the current LLM provider (creates on first call)."""
    global _current_provider
    if _current_provider is None:
        if _provider_type == "pi":
            _current_provider = PiProvider()
        else:
            _current_provider = ApiProvider()
    return _current_provider


def stop_provider() -> None:
    """Stop and clean up the current provider."""
    global _current_provider
    if _current_provider is not None:
        _current_provider.stop()
        _current_provider = None
