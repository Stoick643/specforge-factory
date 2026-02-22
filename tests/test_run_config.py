"""Tests for RunConfig thread-safe provider management."""

from specforge.providers import ApiProvider, PiProvider, RunConfig
from specforge import events


class TestRunConfig:
    def test_creates_api_provider(self):
        config = RunConfig(provider_type="api", model="gpt-4o")
        provider = config.get_provider()
        assert isinstance(provider, ApiProvider)
        config.stop()

    def test_creates_pi_provider(self):
        config = RunConfig(provider_type="pi")
        # PiProvider.__init__ imports PiRpcClient, so just check the type
        provider = config.get_provider()
        assert isinstance(provider, PiProvider)
        # Don't call stop() — would try to stop a non-started subprocess

    def test_isolation(self):
        """Two RunConfigs don't interfere with each other."""
        config1 = RunConfig(provider_type="api", model="gpt-4o")
        config2 = RunConfig(provider_type="api", model="claude-sonnet-4-20250514")

        p1 = config1.get_provider()
        p2 = config2.get_provider()

        # Different instances
        assert p1 is not p2
        # Different models
        assert isinstance(p1, ApiProvider)
        assert isinstance(p2, ApiProvider)
        assert p1._model == "gpt-4o"
        assert p2._model == "claude-sonnet-4-20250514"

        config1.stop()
        config2.stop()

    def test_reuses_provider(self):
        """Same RunConfig returns the same provider instance."""
        config = RunConfig(provider_type="api")
        p1 = config.get_provider()
        p2 = config.get_provider()
        assert p1 is p2
        config.stop()

    def test_stop_clears_provider(self):
        """After stop(), get_provider() creates a new instance."""
        config = RunConfig(provider_type="api")
        p1 = config.get_provider()
        config.stop()
        p2 = config.get_provider()
        assert p1 is not p2
        config.stop()

    def test_api_key_passed_to_provider(self):
        """RunConfig passes api_key to ApiProvider."""
        config = RunConfig(provider_type="api", model="gpt-4o", api_key="sk-test-123")
        provider = config.get_provider()
        assert isinstance(provider, ApiProvider)
        assert provider._api_key == "sk-test-123"
        config.stop()

    def test_on_progress_callback(self):
        """RunConfig can carry a per-run progress callback."""
        received = []
        config = RunConfig(provider_type="api", on_progress=lambda ev: received.append(ev))
        assert config.on_progress is not None
        config.stop()

    def test_get_run_callback_from_state(self):
        """events.get_run_callback extracts callback from state with run_config."""
        received = []
        callback = lambda ev: received.append(ev)
        config = RunConfig(provider_type="api", on_progress=callback)
        state = {"run_config": config}
        assert events.get_run_callback(state) is callback
        config.stop()

    def test_get_run_callback_returns_none_without_config(self):
        """events.get_run_callback returns None when no run_config."""
        assert events.get_run_callback({}) is None

    def test_emit_calls_run_callback(self):
        """events.emit delivers to per-run callback when provided."""
        global_received = []
        run_received = []

        events.add_handler(lambda ev: global_received.append(ev.message))
        try:
            events.emit("test", "info", "hello", _run_callback=lambda ev: run_received.append(ev.message))
            assert "hello" in global_received
            assert "hello" in run_received
        finally:
            events.clear_handlers()

    def test_event_scoping_isolation(self):
        """Two run callbacks only receive their own events."""
        run_a = []
        run_b = []

        cb_a = lambda ev: run_a.append(ev.message)
        cb_b = lambda ev: run_b.append(ev.message)

        events.emit("test", "info", "for-a", _run_callback=cb_a)
        events.emit("test", "info", "for-b", _run_callback=cb_b)

        assert run_a == ["for-a"]
        assert run_b == ["for-b"]
