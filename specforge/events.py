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


def emit(agent: str, event: str, message: str, iteration: int = 0, **data) -> None:
    """Emit a progress event to all registered handlers."""
    ev = ProgressEvent(
        agent=agent,
        event=event,
        message=message,
        iteration=iteration,
        data=data,
    )
    for handler in _handlers:
        handler(ev)
