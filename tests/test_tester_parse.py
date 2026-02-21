"""Tests for Tester agent's pytest output parsing."""

import pytest

from specforge.agents.tester import _parse_pytest_output


class TestParsePytestOutput:
    def test_all_passed(self):
        output = "===== 10 passed in 2.5s ====="
        total, passed, failed, errors = _parse_pytest_output(output)
        assert total == 10
        assert passed == 10
        assert failed == 0
        assert errors == 0

    def test_mixed_results(self):
        output = "===== 5 passed, 3 failed, 1 error in 4.2s ====="
        total, passed, failed, errors = _parse_pytest_output(output)
        assert total == 9
        assert passed == 5
        assert failed == 3
        assert errors == 1

    def test_all_failed(self):
        output = "===== 7 failed in 1.0s ====="
        total, passed, failed, errors = _parse_pytest_output(output)
        assert total == 7
        assert passed == 0
        assert failed == 7

    def test_no_tests(self):
        output = "no tests ran"
        total, passed, failed, errors = _parse_pytest_output(output)
        assert total == 0

    def test_verbose_output(self):
        output = """
tests/test_health.py::test_health PASSED
tests/test_links.py::test_create PASSED
tests/test_links.py::test_delete FAILED
===== 2 passed, 1 failed in 3.0s =====
"""
        total, passed, failed, errors = _parse_pytest_output(output)
        assert passed == 2
        assert failed == 1
        assert total == 3
