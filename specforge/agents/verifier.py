"""Verifier -- Runs 6 post-generation checks to validate the generated project.

Checks:
1. Tests pass — all pytest tests pass with total > 0
2. App starts — FastAPI app can be imported and /health returns 200
3. Docker builds — `docker build .` succeeds
4. Spec coverage — generated endpoints match SystemDesign.endpoints
5. Tests meaningful — minimum test count relative to endpoint count
6. Project structure — essential files exist with correct content
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from specforge import events
from specforge.utils.console import console


@dataclass
class VerificationCheck:
    """Result of a single verification check."""
    name: str
    passed: bool
    details: str
    skipped: bool = False  # True if check couldn't run (e.g., Docker not installed)


@dataclass
class VerificationReport:
    """Aggregated results from all verification checks."""
    checks: list[VerificationCheck] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed and not c.skipped)

    @property
    def skipped_count(self) -> int:
        return sum(1 for c in self.checks if c.skipped)

    @property
    def total_count(self) -> int:
        return len(self.checks)

    @property
    def all_passed(self) -> bool:
        """All non-skipped checks passed."""
        return all(c.passed or c.skipped for c in self.checks)

    def to_dict(self) -> dict:
        return {
            "checks": [
                {"name": c.name, "passed": c.passed, "details": c.details, "skipped": c.skipped}
                for c in self.checks
            ],
            "passed": self.passed_count,
            "failed": self.failed_count,
            "skipped": self.skipped_count,
            "total": self.total_count,
            "all_passed": self.all_passed,
        }


# ── Individual checks ───────────────────────────────────────────────


def check_tests_pass(
    pytest_returncode: int, total: int, failed: int, errors: int
) -> VerificationCheck:
    """Check 1: All pytest tests pass with at least 1 test."""
    if total == 0:
        return VerificationCheck(
            name="Tests pass",
            passed=False,
            details="No tests were collected or run",
        )
    if pytest_returncode != 0 or failed > 0 or errors > 0:
        return VerificationCheck(
            name="Tests pass",
            passed=False,
            details=f"{failed} failed, {errors} errors out of {total} tests",
        )
    return VerificationCheck(
        name="Tests pass",
        passed=True,
        details=f"All {total} tests passed",
    )


def check_app_starts(output_dir: str) -> VerificationCheck:
    """Check 2: FastAPI app can be imported and /health returns 200.

    Runs a quick smoke test in a subprocess to avoid polluting our process.
    """
    venv_python = _get_venv_python(output_dir)
    python_cmd = venv_python if Path(venv_python).exists() else "python"

    # Script that imports the app and makes a test request to /health
    smoke_script = """
import sys
try:
    sys.path.insert(0, '.')
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    resp = client.get('/health')
    if resp.status_code == 200:
        print(f"OK: /health returned {resp.status_code}")
        sys.exit(0)
    else:
        print(f"FAIL: /health returned {resp.status_code}: {resp.text}")
        sys.exit(1)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
"""
    try:
        result = subprocess.run(
            [python_cmd, "-c", smoke_script],
            cwd=output_dir,
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "PYTHONPATH": output_dir},
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0:
            return VerificationCheck(name="App starts", passed=True, details=output)
        return VerificationCheck(name="App starts", passed=False, details=output)
    except subprocess.TimeoutExpired:
        return VerificationCheck(name="App starts", passed=False, details="Timed out after 30s")
    except Exception as e:
        return VerificationCheck(name="App starts", passed=False, details=str(e))


def check_docker_builds(output_dir: str) -> VerificationCheck:
    """Check 3: `docker build .` succeeds in the output directory."""
    dockerfile = Path(output_dir) / "Dockerfile"
    if not dockerfile.exists():
        return VerificationCheck(
            name="Docker builds",
            passed=False,
            details="No Dockerfile found",
        )

    # Check if Docker is available and daemon is running
    try:
        docker_check = subprocess.run(
            ["docker", "ps"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if docker_check.returncode != 0:
            detail = docker_check.stderr.strip().split("\n")[0] if docker_check.stderr else "Docker daemon not running"
            return VerificationCheck(
                name="Docker builds",
                passed=False,
                details=f"Docker not available: {detail}",
                skipped=True,
            )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return VerificationCheck(
            name="Docker builds",
            passed=False,
            details="Docker not available on this system",
            skipped=True,
        )

    try:
        result = subprocess.run(
            ["docker", "build", ".", "-t", "specforge-verify-temp", "--no-cache"],
            cwd=output_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            # Clean up temp image
            subprocess.run(
                ["docker", "rmi", "specforge-verify-temp"],
                capture_output=True,
                timeout=30,
            )
            return VerificationCheck(name="Docker builds", passed=True, details="Docker build succeeded")
        # Extract last few lines of error
        error_lines = result.stderr.strip().split("\n")[-5:]
        return VerificationCheck(
            name="Docker builds",
            passed=False,
            details="Build failed: " + "\n".join(error_lines),
        )
    except subprocess.TimeoutExpired:
        return VerificationCheck(name="Docker builds", passed=False, details="Docker build timed out (300s)")


def check_spec_coverage(
    generated_files: dict[str, str], system_design: dict
) -> VerificationCheck:
    """Check 4: Generated endpoints match SystemDesign.endpoints.

    Scans generated router files for route decorators and compares against
    the endpoints defined in SystemDesign.
    """
    spec_endpoints = system_design.get("endpoints", [])
    if not spec_endpoints:
        return VerificationCheck(
            name="Spec coverage",
            passed=True,
            details="No endpoints in spec to verify",
        )

    # Step 1: Extract router prefixes from main.py
    # Matches: app.include_router(auth_router, prefix="/api/auth")
    prefix_map: dict[str, str] = {}  # router variable name -> prefix
    prefix_pattern = re.compile(
        r'include_router\(\s*(\w+).*?prefix\s*=\s*["\']([^"\']+)["\']',
        re.DOTALL,
    )
    main_content = ""
    for fp, content in generated_files.items():
        if "main.py" in fp:
            main_content = content
            for match in prefix_pattern.finditer(content):
                router_var = match.group(1)
                prefix = match.group(2).rstrip("/")
                prefix_map[router_var] = prefix

    # Step 2: Extract route paths from generated code
    generated_routes: set[str] = set()
    route_pattern = re.compile(
        r'@\w+\.(get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    for filepath, content in generated_files.items():
        if "router" in filepath.lower() or "main.py" in filepath:
            # Try to find which prefix applies to this file
            file_prefix = ""
            if "router" in filepath.lower():
                # Match router file to prefix by checking imports in main.py
                # e.g., "from app.routers.auth import router as auth_router"
                module_name = filepath.replace("/", ".").replace("\\", ".").replace(".py", "")
                for var_name, prefix in prefix_map.items():
                    # Check if main.py imports from this module with this var name
                    import_pattern = re.compile(
                        rf'from\s+{re.escape(module_name)}\s+import.*?{re.escape(var_name)}'
                        rf'|from\s+\S*{re.escape(filepath.split("/")[-1].replace(".py", ""))}\s+import.*?{re.escape(var_name)}'
                    )
                    if import_pattern.search(main_content):
                        file_prefix = prefix
                        break
                # Fallback: try matching by filename convention
                # e.g., routers/auth.py → prefix containing "auth"
                if not file_prefix:
                    basename = filepath.split("/")[-1].replace(".py", "")
                    for var_name, prefix in prefix_map.items():
                        if basename in var_name or basename in prefix:
                            file_prefix = prefix
                            break

            for match in route_pattern.finditer(content):
                method = match.group(1).upper()
                path = match.group(2)
                # Add both the raw path and the prefixed path
                generated_routes.add(f"{method} {path}")
                if file_prefix:
                    full_path = file_prefix + path if path != "/" else file_prefix
                    generated_routes.add(f"{method} {full_path}")

    # Check which spec endpoints are covered
    missing = []
    for ep in spec_endpoints:
        method = ep.get("method", "GET").upper()
        path = ep.get("path", "")
        # Normalize path — generated code might use slightly different param names
        normalized_spec = f"{method} {path}"
        # Check if any generated route matches (allowing param name differences)
        spec_pattern = re.sub(r'\{[^}]+\}', r'{[^}]+}', re.escape(path))
        spec_regex = re.compile(f"^{method} {spec_pattern}$")
        found = any(spec_regex.match(r) for r in generated_routes)
        if not found:
            missing.append(f"{method} {path}")

    coverage = len(spec_endpoints) - len(missing)
    total = len(spec_endpoints)
    pct = (coverage / total * 100) if total else 100

    if missing:
        missing_str = ", ".join(missing[:10])
        if len(missing) > 10:
            missing_str += f" (+{len(missing) - 10} more)"
        return VerificationCheck(
            name="Spec coverage",
            passed=False,
            details=f"{coverage}/{total} endpoints covered ({pct:.0f}%). Missing: {missing_str}",
        )

    return VerificationCheck(
        name="Spec coverage",
        passed=True,
        details=f"All {total} spec endpoints found in generated code ({len(generated_routes)} routes total)",
    )


def check_tests_meaningful(
    total_tests: int, system_design: dict
) -> VerificationCheck:
    """Check 5: Minimum test count based on endpoint count.

    Heuristic: at least 1 test per endpoint, minimum 3 total.
    """
    endpoint_count = len(system_design.get("endpoints", []))
    min_tests = max(3, endpoint_count)

    if total_tests >= min_tests:
        return VerificationCheck(
            name="Tests meaningful",
            passed=True,
            details=f"{total_tests} tests for {endpoint_count} endpoints (minimum: {min_tests})",
        )
    return VerificationCheck(
        name="Tests meaningful",
        passed=False,
        details=f"Only {total_tests} tests for {endpoint_count} endpoints (expected at least {min_tests})",
    )


def check_project_structure(generated_files: dict[str, str]) -> VerificationCheck:
    """Check 6: Essential files exist with correct content."""
    issues = []

    # Must have app/main.py
    has_main = any("main.py" in fp for fp in generated_files)
    if not has_main:
        issues.append("Missing app/main.py")

    # Must have requirements.txt with fastapi
    req_files = {fp: c for fp, c in generated_files.items() if "requirements.txt" in fp}
    if not req_files:
        issues.append("Missing requirements.txt")
    else:
        req_content = next(iter(req_files.values()))
        if "fastapi" not in req_content.lower():
            issues.append("requirements.txt missing 'fastapi'")

    # Must have at least one test file
    test_files = [fp for fp in generated_files if fp.startswith("tests/") and fp.endswith(".py") and fp != "tests/__init__.py"]
    if not test_files:
        issues.append("No test files in tests/")

    # Must have Dockerfile
    has_dockerfile = any("Dockerfile" in fp for fp in generated_files)
    if not has_dockerfile:
        issues.append("Missing Dockerfile")

    # Must have conftest.py for tests
    has_conftest = any("conftest.py" in fp for fp in generated_files)
    if not has_conftest:
        issues.append("Missing tests/conftest.py")

    if issues:
        return VerificationCheck(
            name="Project structure",
            passed=False,
            details="; ".join(issues),
        )
    return VerificationCheck(
        name="Project structure",
        passed=True,
        details=f"{len(generated_files)} files, all essential files present",
    )


# ── Main entry point ────────────────────────────────────────────────


def run_verification(
    output_dir: str,
    generated_files: dict[str, str],
    system_design: dict,
    pytest_returncode: int,
    total_tests: int,
    failed_tests: int,
    error_tests: int,
    run_docker_check: bool = True,
) -> VerificationReport:
    """Run all 6 verification checks and return a report."""
    report = VerificationReport()

    console.print("\n[bold]Running verification checks...[/bold]")
    events.emit("verifier", "start", "Running verification checks...")

    # Check 1: Tests pass
    console.print("  Checking: Tests pass...")
    report.checks.append(check_tests_pass(pytest_returncode, total_tests, failed_tests, error_tests))

    # Check 2: App starts
    console.print("  Checking: App starts...")
    report.checks.append(check_app_starts(output_dir))

    # Check 3: Docker builds
    if run_docker_check:
        console.print("  Checking: Docker builds...")
        report.checks.append(check_docker_builds(output_dir))
    else:
        report.checks.append(VerificationCheck(
            name="Docker builds", passed=False, details="Skipped", skipped=True
        ))

    # Check 4: Spec coverage
    console.print("  Checking: Spec coverage...")
    report.checks.append(check_spec_coverage(generated_files, system_design))

    # Check 5: Tests meaningful
    console.print("  Checking: Tests meaningful...")
    report.checks.append(check_tests_meaningful(total_tests, system_design))

    # Check 6: Project structure
    console.print("  Checking: Project structure...")
    report.checks.append(check_project_structure(generated_files))

    events.emit("verifier", "done", f"{report.passed_count}/{report.total_count} checks passed",
                 **report.to_dict())

    return report


def print_verification_report(report: VerificationReport) -> None:
    """Print a Rich table with the verification results."""
    from rich.table import Table

    table = Table(title="Verification Report", show_lines=True)
    table.add_column("Check", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Details")

    for check in report.checks:
        if check.skipped:
            status = "⏭️ Skip"
            style = "dim"
        elif check.passed:
            status = "✅ Pass"
            style = "green"
        else:
            status = "❌ Fail"
            style = "red"

        table.add_row(check.name, status, check.details, style=style)

    # Summary row
    summary = f"{report.passed_count} passed, {report.failed_count} failed"
    if report.skipped_count:
        summary += f", {report.skipped_count} skipped"
    table.add_row("TOTAL", "✅" if report.all_passed else "❌", summary, style="bold")

    console.print()
    console.print(table)


# ── Helper ──────────────────────────────────────────────────────────

def _get_venv_python(output_dir: str) -> str:
    """Get the path to the venv's Python executable."""
    venv_dir = Path(output_dir) / ".venv"
    if os.name == "nt":
        return str(venv_dir / "Scripts" / "python.exe")
    return str(venv_dir / "bin" / "python")
