"""Tests for RunConfig thread-safe provider management."""

from specforge.providers import ApiProvider, PiProvider, RunConfig


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
