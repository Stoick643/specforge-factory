"""Progress event system for SpecForge.

Emits structured events that can be consumed by CLI (Rich console) or Web (WebSocket).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Callable


@dataclass
class ProgressEvent:
    """A structured progress event from the workflow."""
    agent: str          # "architect", "coder", "tester", "workflow"
    event: str          # "start", "progress", "done", "error", "test_results"
    message: str        # Human-readable message
    iteration: int = 0
    data: dict = field(default_factory=dict)  # Extra data (test counts, file list, etc.)

    def to_dict(self) -> dict:
        return asdict(self)


# Type for event handler callbacks
EventHandler = Callable[[ProgressEvent], None]

# Global event handlers
_handlers: list[EventHandler] = []


def add_handler(handler: EventHandler) -> None:
    """Register an event handler."""
    _handlers.append(handler)


def remove_handler(handler: EventHandler) -> None:
    """Remove an event handler."""
    if handler in _handlers:
        _handlers.remove(handler)


def clear_handlers() -> None:
    """Remove all event handlers."""
    _handlers.clear()


def emit(agent: str, event: str, message: str, iteration: int = 0,
         _run_callback: Callable[[ProgressEvent], None] | None = None, **data) -> None:
    """Emit a progress event to all registered handlers and optional per-run callback.

    Args:
        agent: Agent name (architect, coder, tester, etc.)
        event: Event type (start, progress, done, error, etc.)
        message: Human-readable message.
        iteration: Current iteration number.
        _run_callback: Per-run callback for scoped event delivery (e.g. Web UI).
            When set, this callback receives the event in addition to global handlers.
        **data: Extra data to include in the event.
    """
    ev = ProgressEvent(
        agent=agent,
        event=event,
        message=message,
        iteration=iteration,
        data=data,
    )
    for handler in _handlers:
        handler(ev)
    if _run_callback is not None:
        _run_callback(ev)


def get_run_callback(state: dict) -> Callable[[ProgressEvent], None] | None:
    """Extract the on_progress callback from agent state, if available.

    Usage in agents:
        cb = events.get_run_callback(state)
        events.emit("agent", "start", "msg", _run_callback=cb)
    """
    run_config = state.get("run_config")
    if run_config is not None and hasattr(run_config, "on_progress"):
        return run_config.on_progress
    return None
