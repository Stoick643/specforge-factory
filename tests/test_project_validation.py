"""Tests for generated project validation."""

from specforge.agents.tester import _validate_project


class TestProjectValidation:
    def test_valid_project(self):
        """Complete project passes validation."""
        files = {
            "app/main.py": "from fastapi import FastAPI\napp = FastAPI()",
            "app/models.py": "from sqlmodel import SQLModel",
            "requirements.txt": "fastapi==0.115.0\nuvicorn==0.30.0",
            "tests/__init__.py": "",
            "tests/conftest.py": "import pytest",
            "tests/test_health.py": "def test_health(): pass",
            "Dockerfile": "FROM python:3.12-slim",
        }
        warnings = _validate_project(files)
        assert warnings == []

    def test_missing_main(self):
        """Warns when app/main.py is missing."""
        files = {
            "app/models.py": "...",
            "requirements.txt": "fastapi",
            "tests/test_health.py": "...",
            "Dockerfile": "FROM python:3.12-slim",
        }
        warnings = _validate_project(files)
        assert any("main.py" in w for w in warnings)

    def test_missing_fastapi_in_requirements(self):
        """Warns when requirements.txt exists but doesn't include fastapi."""
        files = {
            "app/main.py": "...",
            "requirements.txt": "flask==3.0.0\nuvicorn==0.30.0",
            "tests/test_health.py": "...",
            "Dockerfile": "FROM python:3.12-slim",
        }
        warnings = _validate_project(files)
        assert any("fastapi" in w for w in warnings)

    def test_missing_tests(self):
        """Warns when no test files exist."""
        files = {
            "app/main.py": "...",
            "requirements.txt": "fastapi",
            "tests/__init__.py": "",
            "Dockerfile": "FROM python:3.12-slim",
        }
        warnings = _validate_project(files)
        assert any("test files" in w.lower() for w in warnings)

    def test_missing_dockerfile(self):
        """Warns when Dockerfile is missing."""
        files = {
            "app/main.py": "...",
            "requirements.txt": "fastapi",
            "tests/test_health.py": "...",
        }
        warnings = _validate_project(files)
        assert any("Dockerfile" in w for w in warnings)

    def test_missing_requirements(self):
        """Warns when requirements.txt is missing entirely."""
        files = {
            "app/main.py": "...",
            "tests/test_health.py": "...",
            "Dockerfile": "FROM python:3.12-slim",
        }
        warnings = _validate_project(files)
        assert any("requirements.txt" in w for w in warnings)
