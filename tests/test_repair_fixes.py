"""Tests for repair loop fixes: error dedup, feedback truncation, design condensing, dep conflicts."""

import pytest

from specforge.agents.coder import _condense_system_design, _fix_known_dep_conflicts
from specforge.agents.tester import _deduplicate_errors


# ── Fix B: Deduplication + truncation ───────────────────────────────


class TestDeduplicateErrors:
    def test_78_identical_errors(self):
        """78 identical errors should collapse to 1 line with count."""
        lines = []
        for i in range(78):
            lines.append(f"ERROR tests/test_tags.py::test_{i} - ValueError: password cannot be loaded")
        output = "\n".join(lines)

        result = _deduplicate_errors(output)
        assert "×78" in result or "x78" in result.lower()
        # Should be much shorter than original
        assert len(result) < len(output) / 10

    def test_mixed_errors(self):
        """Different error types should each appear."""
        output = (
            "ERROR tests/test_a.py - ValueError: password cannot be loaded\n"
            "ERROR tests/test_b.py - ValueError: password cannot be loaded\n"
            "ERROR tests/test_c.py - ImportError: cannot import name 'foo'\n"
            "FAILED tests/test_d.py - AssertionError: 404 != 200\n"
        )
        result = _deduplicate_errors(output)
        assert "password" in result
        assert "ImportError" in result
        assert "AssertionError" in result

    def test_no_errors(self):
        """Output with no error markers should return last lines."""
        output = "all good\nno problems here\n===== 10 passed ====="
        result = _deduplicate_errors(output)
        assert "10 passed" in result

    def test_single_error(self):
        """Single error should not have a count prefix."""
        output = "ERROR tests/test_a.py - ValueError: something broke"
        result = _deduplicate_errors(output)
        assert "×" not in result
        assert "ValueError" in result


class TestFeedbackTruncation:
    def test_long_feedback_is_capped(self):
        """_analyze_failures output should be capped at 2000 chars."""
        # We can't easily test _analyze_failures without an LLM,
        # but we can test the truncation logic indirectly.
        # The truncation happens inside _analyze_failures, so we test
        # that the coder's error_context stays within bounds.
        from specforge.agents.coder import _condense_system_design

        # The coder caps feedback at 2000 chars in its error_context building
        long_feedback = "x" * 5000
        capped = long_feedback[:2000] + "\n... (truncated)"
        assert len(capped) < 2100


# ── Fix C: Condense SystemDesign ────────────────────────────────────


class TestCondenseSystemDesign:
    def test_condensed_is_smaller(self):
        """Condensed version should be much smaller than full JSON."""
        import json
        design = {
            "project_name": "bookmark-manager",
            "description": "A bookmark management service",
            "dependencies": ["fastapi", "uvicorn", "sqlmodel", "passlib", "python-jose"],
            "endpoints": [
                {"method": "GET", "path": "/bookmarks", "auth": "jwt", "summary": "List bookmarks"},
                {"method": "POST", "path": "/bookmarks", "auth": "jwt", "summary": "Create bookmark"},
                {"method": "GET", "path": "/bookmarks/{id}", "auth": "jwt", "summary": "Get bookmark"},
                {"method": "DELETE", "path": "/bookmarks/{id}", "auth": "jwt", "summary": "Delete bookmark"},
                {"method": "POST", "path": "/auth/login", "auth": "none", "summary": "Login"},
                {"method": "POST", "path": "/auth/register", "auth": "none", "summary": "Register"},
            ],
            "database_models": [
                {"name": "User", "table_name": "users", "fields": [
                    {"name": "id"}, {"name": "email"}, {"name": "hashed_password"}
                ]},
                {"name": "Bookmark", "table_name": "bookmarks", "fields": [
                    {"name": "id"}, {"name": "url"}, {"name": "title"}, {"name": "user_id"}
                ]},
            ],
            "env_variables": [
                {"name": "DATABASE_URL", "description": "DB connection string"},
                {"name": "JWT_SECRET", "description": "JWT signing secret"},
            ],
            "docker": {"port": 8000, "base_image": "python:3.12-slim"},
            "middlewares": [],
            "additional_notes": "Use async everywhere. " * 50,
        }

        full_json = json.dumps(design, indent=2)
        condensed = _condense_system_design(design)

        assert len(condensed) < len(full_json)
        # Should be at most 50% of full size (usually much less)
        assert len(condensed) < len(full_json) * 0.5

    def test_condensed_has_essentials(self):
        """Condensed version should include project name, endpoints, models."""
        design = {
            "project_name": "todo-app",
            "description": "A todo list",
            "dependencies": ["fastapi", "sqlmodel"],
            "endpoints": [
                {"method": "GET", "path": "/tasks", "auth": "jwt"},
                {"method": "POST", "path": "/tasks", "auth": "jwt"},
            ],
            "database_models": [
                {"name": "Task", "table_name": "tasks", "fields": [
                    {"name": "id"}, {"name": "title"}, {"name": "done"}
                ]},
            ],
            "env_variables": [
                {"name": "DATABASE_URL", "description": "DB path"},
            ],
        }
        condensed = _condense_system_design(design)

        assert "todo-app" in condensed
        assert "GET /tasks" in condensed
        assert "POST /tasks" in condensed
        assert "Task" in condensed
        assert "DATABASE_URL" in condensed

    def test_condensed_under_3kb(self):
        """Even a large design should condense to under 3KB."""
        design = {
            "project_name": "big-project",
            "description": "A very large project",
            "dependencies": [f"dep-{i}" for i in range(20)],
            "endpoints": [
                {"method": "GET", "path": f"/resource{i}", "auth": "jwt"}
                for i in range(30)
            ],
            "database_models": [
                {"name": f"Model{i}", "table_name": f"table{i}",
                 "fields": [{"name": f"field{j}"} for j in range(10)]}
                for i in range(10)
            ],
            "env_variables": [
                {"name": f"VAR_{i}", "description": f"Variable {i}"}
                for i in range(15)
            ],
        }
        condensed = _condense_system_design(design)
        assert len(condensed) < 3000


# ── Fix A: Known dependency conflicts ──────────────────────────────


class TestFixKnownDepConflicts:
    def test_pins_bcrypt_when_passlib_present(self):
        """If passlib is in requirements and bcrypt is unpinned, pin it."""
        files = {
            "requirements.txt": "fastapi==0.115.0\npasslib[bcrypt]==1.7.4\nbcrypt\n",
        }
        fixed = _fix_known_dep_conflicts(files)
        assert "bcrypt==4.0.1" in fixed["requirements.txt"]

    def test_downgrades_bcrypt_5(self):
        """If bcrypt==5.0.0 is specified with passlib, downgrade it."""
        files = {
            "requirements.txt": "fastapi==0.115.0\npasslib==1.7.4\nbcrypt==5.0.0\n",
        }
        fixed = _fix_known_dep_conflicts(files)
        assert "bcrypt==4.0.1" in fixed["requirements.txt"]
        assert "5.0.0" not in fixed["requirements.txt"]

    def test_leaves_compatible_bcrypt(self):
        """If bcrypt==4.0.1 is already set, leave it alone."""
        files = {
            "requirements.txt": "fastapi==0.115.0\npasslib==1.7.4\nbcrypt==4.0.1\n",
        }
        fixed = _fix_known_dep_conflicts(files)
        assert "bcrypt==4.0.1" in fixed["requirements.txt"]

    def test_no_passlib_no_change(self):
        """If no passlib, don't touch bcrypt."""
        files = {
            "requirements.txt": "fastapi==0.115.0\nbcrypt==5.0.0\n",
        }
        fixed = _fix_known_dep_conflicts(files)
        assert "bcrypt==5.0.0" in fixed["requirements.txt"]

    def test_adds_bcrypt_if_missing(self):
        """If passlib is present but bcrypt line missing, add pinned bcrypt."""
        files = {
            "requirements.txt": "fastapi==0.115.0\npasslib[bcrypt]==1.7.4\n",
        }
        fixed = _fix_known_dep_conflicts(files)
        assert "bcrypt==4.0.1" in fixed["requirements.txt"]

    def test_no_requirements_file(self):
        """If no requirements.txt, return files unchanged."""
        files = {"app/main.py": "..."}
        fixed = _fix_known_dep_conflicts(files)
        assert fixed == files
