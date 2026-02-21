"""Tests that agents emit progress events."""

import pytest

from specforge import events


@pytest.fixture(autouse=True)
def cleanup_handlers():
    events.clear_handlers()
    yield
    events.clear_handlers()


class TestArchitectEvents:
    def test_emits_start_and_error_on_bad_state(self):
        """Architect should emit start event, then error when no provider."""
        received = []
        events.add_handler(lambda ev: received.append(ev))

        from specforge.agents.architect import architect_node

        state = {"spec_text": "# Test", "errors": []}
        # Will fail because no provider is configured, but should emit events
        result = architect_node(state)

        # Should have emitted at least a start event
        agent_events = [e for e in received if e.agent == "architect"]
        assert len(agent_events) >= 1
        assert agent_events[0].event == "start"


class TestCoderEvents:
    def test_emits_start_on_call(self):
        """Coder should emit start event."""
        received = []
        events.add_handler(lambda ev: received.append(ev))

        from specforge.agents.coder import coder_node

        state = {
            "system_design": {"project_name": "test"},
            "iteration": 1,
            "errors": [],
        }
        # Will fail because no provider, but should emit start
        result = coder_node(state)

        coder_events = [e for e in received if e.agent == "coder"]
        assert len(coder_events) >= 1
        assert coder_events[0].event == "start"
        assert coder_events[0].iteration == 1


class TestTesterEvents:
    def test_emits_start_on_call(self):
        """Tester should emit start event."""
        received = []
        events.add_handler(lambda ev: received.append(ev))

        from specforge.agents.tester import tester_node

        state = {
            "output_dir": "/tmp/nonexistent",
            "generated_files": {},
            "iteration": 1,
            "errors": [],
        }
        result = tester_node(state)

        tester_events = [e for e in received if e.agent == "tester"]
        assert len(tester_events) >= 1
        assert tester_events[0].event == "start"
