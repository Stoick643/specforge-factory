"""Tests for the progress event system."""

import pytest

from specforge.events import (
    ProgressEvent,
    add_handler,
    clear_handlers,
    emit,
    remove_handler,
)


@pytest.fixture(autouse=True)
def cleanup_handlers():
    """Ensure handlers are cleared between tests."""
    clear_handlers()
    yield
    clear_handlers()


class TestProgressEvent:
    def test_create_event(self):
        ev = ProgressEvent(agent="architect", event="start", message="Starting")
        assert ev.agent == "architect"
        assert ev.event == "start"
        assert ev.message == "Starting"
        assert ev.iteration == 0
        assert ev.data == {}

    def test_to_dict(self):
        ev = ProgressEvent(
            agent="coder", event="progress", message="Generating",
            iteration=2, data={"files": 7}
        )
        d = ev.to_dict()
        assert d["agent"] == "coder"
        assert d["event"] == "progress"
        assert d["iteration"] == 2
        assert d["data"]["files"] == 7


class TestHandlers:
    def test_add_and_emit(self):
        received = []
        add_handler(lambda ev: received.append(ev))

        emit("architect", "start", "Analyzing spec")

        assert len(received) == 1
        assert received[0].agent == "architect"
        assert received[0].message == "Analyzing spec"

    def test_multiple_handlers(self):
        received_a = []
        received_b = []
        add_handler(lambda ev: received_a.append(ev))
        add_handler(lambda ev: received_b.append(ev))

        emit("coder", "done", "Generated 24 files")

        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_remove_handler(self):
        received = []
        handler = lambda ev: received.append(ev)
        add_handler(handler)
        remove_handler(handler)

        emit("tester", "start", "Running tests")

        assert len(received) == 0

    def test_clear_handlers(self):
        received = []
        add_handler(lambda ev: received.append(ev))
        add_handler(lambda ev: received.append(ev))
        clear_handlers()

        emit("architect", "start", "Test")

        assert len(received) == 0

    def test_emit_with_extra_data(self):
        received = []
        add_handler(lambda ev: received.append(ev))

        emit("tester", "test_results", "46/49 passed",
             iteration=1, passed=46, failed=3, total=49)

        ev = received[0]
        assert ev.data["passed"] == 46
        assert ev.data["failed"] == 3
        assert ev.data["total"] == 49
        assert ev.iteration == 1

    def test_no_handlers_no_error(self):
        # Should not raise even with no handlers
        emit("architect", "start", "No one listening")
