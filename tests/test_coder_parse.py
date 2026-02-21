"""Tests for Coder agent's JSON parsing logic."""

import pytest

from specforge.agents.coder import _parse_files_response


class TestParseFilesResponse:
    def test_plain_json(self):
        content = '{"app/main.py": "print(1)", "tests/test.py": "assert True"}'
        result = _parse_files_response(content)
        assert result == {"app/main.py": "print(1)", "tests/test.py": "assert True"}

    def test_json_with_code_fence(self):
        content = '```json\n{"app/main.py": "print(1)"}\n```'
        result = _parse_files_response(content)
        assert result == {"app/main.py": "print(1)"}

    def test_json_with_plain_fence(self):
        content = '```\n{"app/main.py": "code"}\n```'
        result = _parse_files_response(content)
        assert result == {"app/main.py": "code"}

    def test_invalid_json(self):
        with pytest.raises(Exception):
            _parse_files_response("not json at all")

    def test_whitespace_handling(self):
        content = '  \n  {"a.py": "x"}  \n  '
        result = _parse_files_response(content)
        assert result == {"a.py": "x"}

    def test_text_before_json(self):
        """Pi/Claude often adds explanation before the JSON."""
        content = (
            'Let me analyze the errors and fix them.\n\n'
            'Here are the corrected files:\n\n'
            '```json\n{"app/main.py": "fixed code"}\n```'
        )
        result = _parse_files_response(content)
        assert result == {"app/main.py": "fixed code"}

    def test_text_before_bare_json(self):
        """Text before JSON without code fences."""
        content = (
            'Looking at the error, the fix is:\n\n'
            '{"app/main.py": "fixed"}'
        )
        result = _parse_files_response(content)
        assert result == {"app/main.py": "fixed"}

    def test_text_after_json(self):
        """Text after JSON."""
        content = '{"app/main.py": "code"}\n\nAll files are now fixed.'
        result = _parse_files_response(content)
        assert result == {"app/main.py": "code"}
