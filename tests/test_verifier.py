"""Tests for the verification checks."""

import pytest

from specforge.agents.verifier import (
    VerificationReport,
    check_project_structure,
    check_spec_coverage,
    check_tests_meaningful,
    check_tests_pass,
)


# ── Check 1: Tests pass ────────────────────────────────────────────


class TestCheckTestsPass:
    def test_all_pass(self):
        result = check_tests_pass(pytest_returncode=0, total=10, failed=0, errors=0)
        assert result.passed
        assert "10" in result.details

    def test_some_fail(self):
        result = check_tests_pass(pytest_returncode=1, total=10, failed=3, errors=0)
        assert not result.passed
        assert "3 failed" in result.details

    def test_no_tests(self):
        result = check_tests_pass(pytest_returncode=0, total=0, failed=0, errors=0)
        assert not result.passed
        assert "No tests" in result.details

    def test_errors(self):
        result = check_tests_pass(pytest_returncode=1, total=5, failed=0, errors=2)
        assert not result.passed
        assert "2 errors" in result.details


# ── Check 4: Spec coverage ─────────────────────────────────────────


class TestCheckSpecCoverage:
    def test_full_coverage(self):
        files = {
            "app/routers/tasks.py": '@router.get("/tasks")\n@router.post("/tasks")\n',
        }
        design = {
            "endpoints": [
                {"method": "GET", "path": "/tasks"},
                {"method": "POST", "path": "/tasks"},
            ]
        }
        result = check_spec_coverage(files, design)
        assert result.passed
        assert "2" in result.details

    def test_missing_endpoint(self):
        files = {
            "app/routers/tasks.py": '@router.get("/tasks")\n',
        }
        design = {
            "endpoints": [
                {"method": "GET", "path": "/tasks"},
                {"method": "POST", "path": "/tasks"},
                {"method": "DELETE", "path": "/tasks/{id}"},
            ]
        }
        result = check_spec_coverage(files, design)
        assert not result.passed
        assert "Missing" in result.details

    def test_path_params_match(self):
        """Path parameters like {id} vs {task_id} should still match."""
        files = {
            "app/routers/tasks.py": '@router.get("/tasks/{task_id}")\n',
        }
        design = {
            "endpoints": [
                {"method": "GET", "path": "/tasks/{id}"},
            ]
        }
        result = check_spec_coverage(files, design)
        assert result.passed

    def test_empty_spec(self):
        result = check_spec_coverage({}, {"endpoints": []})
        assert result.passed

    def test_router_prefix_in_main(self):
        """Routes defined in main.py should also be found."""
        files = {
            "app/main.py": '@app.get("/health")\ndef health(): pass\n',
        }
        design = {
            "endpoints": [
                {"method": "GET", "path": "/health"},
            ]
        }
        result = check_spec_coverage(files, design)
        assert result.passed

    def test_router_with_include_prefix(self):
        """Routes with include_router prefix should be combined correctly."""
        files = {
            "app/main.py": (
                'from app.routers.auth import router as auth_router\n'
                'app.include_router(auth_router, prefix="/api/auth")\n'
            ),
            "app/routers/auth.py": (
                '@router.post("/register")\n'
                'def register(): pass\n'
                '@router.post("/login")\n'
                'def login(): pass\n'
            ),
        }
        design = {
            "endpoints": [
                {"method": "POST", "path": "/api/auth/register"},
                {"method": "POST", "path": "/api/auth/login"},
            ]
        }
        result = check_spec_coverage(files, design)
        assert result.passed, f"Expected pass but got: {result.details}"

    def test_router_with_apirouter_prefix(self):
        """Routes with APIRouter(prefix=...) should be combined correctly."""
        files = {
            "app/main.py": (
                'from app.routers import auth, bookmarks\n'
                'app.include_router(auth.router)\n'
                'app.include_router(bookmarks.router)\n'
            ),
            "app/routers/auth.py": (
                'router = APIRouter(prefix="/api/auth", tags=["Auth"])\n'
                '@router.post("/register")\n'
                'def register(): pass\n'
                '@router.post("/login")\n'
                'def login(): pass\n'
            ),
            "app/routers/bookmarks.py": (
                'router = APIRouter(prefix="/api/bookmarks", tags=["Bookmarks"])\n'
                '@router.get("/")\n'
                'def list_bookmarks(): pass\n'
                '@router.post("/")\n'
                'def create_bookmark(): pass\n'
                '@router.get("/{bookmark_id}")\n'
                'def get_bookmark(): pass\n'
            ),
        }
        design = {
            "endpoints": [
                {"method": "POST", "path": "/api/auth/register"},
                {"method": "POST", "path": "/api/auth/login"},
                {"method": "GET", "path": "/api/bookmarks"},
                {"method": "POST", "path": "/api/bookmarks"},
                {"method": "GET", "path": "/api/bookmarks/{id}"},
            ]
        }
        result = check_spec_coverage(files, design)
        assert result.passed, f"Expected pass but got: {result.details}"


# ── Check 5: Tests meaningful ───────────────────────────────────────


class TestCheckTestsMeaningful:
    def test_enough_tests(self):
        design = {"endpoints": [{"path": f"/ep{i}"} for i in range(5)]}
        result = check_tests_meaningful(total_tests=8, system_design=design)
        assert result.passed

    def test_too_few_tests(self):
        design = {"endpoints": [{"path": f"/ep{i}"} for i in range(10)]}
        result = check_tests_meaningful(total_tests=3, system_design=design)
        assert not result.passed
        assert "expected at least 10" in result.details

    def test_minimum_3(self):
        """Even with 1 endpoint, need at least 3 tests."""
        design = {"endpoints": [{"path": "/health"}]}
        result = check_tests_meaningful(total_tests=2, system_design=design)
        assert not result.passed
        assert "at least 3" in result.details

    def test_no_endpoints(self):
        design = {"endpoints": []}
        result = check_tests_meaningful(total_tests=5, system_design=design)
        assert result.passed


# ── Check 6: Project structure ──────────────────────────────────────


class TestCheckProjectStructure:
    def test_complete_project(self):
        files = {
            "app/main.py": "from fastapi import FastAPI",
            "requirements.txt": "fastapi==0.115.0",
            "tests/conftest.py": "import pytest",
            "tests/test_health.py": "def test(): pass",
            "Dockerfile": "FROM python:3.12-slim",
        }
        result = check_project_structure(files)
        assert result.passed

    def test_missing_main(self):
        files = {
            "requirements.txt": "fastapi",
            "tests/test_health.py": "...",
            "tests/conftest.py": "...",
            "Dockerfile": "FROM python:3.12-slim",
        }
        result = check_project_structure(files)
        assert not result.passed
        assert "main.py" in result.details

    def test_missing_conftest(self):
        files = {
            "app/main.py": "...",
            "requirements.txt": "fastapi",
            "tests/test_health.py": "...",
            "Dockerfile": "FROM python:3.12-slim",
        }
        result = check_project_structure(files)
        assert not result.passed
        assert "conftest" in result.details


# ── VerificationReport ──────────────────────────────────────────────


class TestVerificationReport:
    def test_all_passed(self):
        from specforge.agents.verifier import VerificationCheck
        report = VerificationReport(checks=[
            VerificationCheck(name="A", passed=True, details="ok"),
            VerificationCheck(name="B", passed=True, details="ok"),
        ])
        assert report.all_passed
        assert report.passed_count == 2
        assert report.failed_count == 0

    def test_some_failed(self):
        from specforge.agents.verifier import VerificationCheck
        report = VerificationReport(checks=[
            VerificationCheck(name="A", passed=True, details="ok"),
            VerificationCheck(name="B", passed=False, details="bad"),
        ])
        assert not report.all_passed
        assert report.passed_count == 1
        assert report.failed_count == 1

    def test_skipped_dont_fail(self):
        from specforge.agents.verifier import VerificationCheck
        report = VerificationReport(checks=[
            VerificationCheck(name="A", passed=True, details="ok"),
            VerificationCheck(name="B", passed=False, details="skip", skipped=True),
        ])
        assert report.all_passed
        assert report.skipped_count == 1

    def test_to_dict(self):
        from specforge.agents.verifier import VerificationCheck
        report = VerificationReport(checks=[
            VerificationCheck(name="A", passed=True, details="ok"),
        ])
        d = report.to_dict()
        assert d["passed"] == 1
        assert d["all_passed"] is True
        assert len(d["checks"]) == 1
