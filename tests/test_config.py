"""Tests for SpecForge config module."""

import os
from unittest.mock import patch

import pytest

from specforge.config import get_model, set_model, validate_api_key


class TestModelConfig:
    def setup_method(self):
        set_model("gpt-4o")  # Reset to default

    def test_default_model(self):
        assert get_model() == "gpt-4o"

    def test_set_model(self):
        set_model("claude-sonnet-4-20250514")
        assert get_model() == "claude-sonnet-4-20250514"

    def test_set_model_openai(self):
        set_model("gpt-4o-mini")
        assert get_model() == "gpt-4o-mini"


class TestApiKeyValidation:
    def setup_method(self):
        set_model("gpt-4o")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-real-key-12345"}, clear=False)
    def test_valid_openai_key(self):
        valid, msg = validate_api_key()
        assert valid is True
        assert msg == ""

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False)
    def test_missing_openai_key(self):
        # Remove key if present
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            valid, msg = validate_api_key()
            assert valid is False
            assert "OPENAI_API_KEY" in msg

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-your-openai-key-here"}, clear=False)
    def test_placeholder_openai_key(self):
        valid, msg = validate_api_key()
        assert valid is False

    def test_anthropic_key_validation(self):
        set_model("claude-sonnet-4-20250514")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-real-key"}, clear=False):
            valid, msg = validate_api_key()
            assert valid is True

    def test_missing_anthropic_key(self):
        set_model("claude-sonnet-4-20250514")
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            valid, msg = validate_api_key()
            assert valid is False
            assert "ANTHROPIC_API_KEY" in msg
