"""Tester Agent -- Writes generated files to disk, runs pytest, analyzes results."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from specforge import events
from specforge.models import AgentState, TestRunResult
from specforge.prompts.tester import ANALYSIS_PROMPT
from specforge.providers import get_provider as get_global_provider
from specforge.utils.console import (
    console,
    print_agent_done,
    print_agent_error,
    print_agent_start,
    print_test_results,
)


def _write_files(output_dir: str, files: dict[str, str]) -> None:
    """Write generated files to disk."""
    base = Path(output_dir)
    for filepath, content in files.items():
        full_path = base / filepath
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")


def _run_pytest(output_dir: str) -> tuple[int, str]:
    """Run pytest in the output directory using the project's venv."""
    env = os.environ.copy()
    env["PYTHONPATH"] = output_dir

    venv_python = _get_venv_python(output_dir)

    # Use venv Python if available, fall back to system Python
    python_cmd = venv_python if Path(venv_python).exists() else "python"

    result = subprocess.run(
        [python_cmd, "-m", "pytest", "-v", "--tb=short", "--no-header"],
        cwd=output_dir,
        capture_output=True,
        text=True,
        timeout=_get_pytest_timeout(),
        env=env,
    )
    output = result.stdout + "\n" + result.stderr
    return result.returncode, output


def _parse_pytest_output(output: str) -> tuple[int, int, int, int]:
    """Parse pytest output to extract test counts.

    Returns (total, passed, failed, errors).
    """
    passed = failed = errors = 0

    match = re.search(r"(\d+) passed", output)
    if match:
        passed = int(match.group(1))

    match = re.search(r"(\d+) failed", output)
    if match:
        failed = int(match.group(1))

    match = re.search(r"(\d+) error", output)
    if match:
        errors = int(match.group(1))

    total = passed + failed + errors
    return total, passed, failed, errors


def _deduplicate_errors(pytest_output: str) -> str:
    """Extract unique error types from pytest output with counts.

    Turns 78 identical 'ValueError: password cannot be loaded' lines
    into '(×78) ValueError: password cannot be loaded'.
    """
    from collections import Counter

    error_lines: list[str] = []
    for line in pytest_output.split("\n"):
        line = line.strip()
        # Match common error patterns
        if any(marker in line for marker in ("Error:", "Exception:", "FAILED", "ImportError")):
            # Normalize: strip test name prefix, keep just the error
            if " - " in line:
                error_part = line.split(" - ", 1)[1].strip()
            elif "ERROR " in line:
                error_part = line
            elif "FAILED " in line:
                error_part = line
            else:
                error_part = line
            error_lines.append(error_part)

    if not error_lines:
        # Fall back to last 20 lines
        lines = [l.strip() for l in pytest_output.strip().split("\n") if l.strip()]
        return "\n".join(lines[-20:])

    # Count unique errors
    counts = Counter(error_lines)
    deduped = []
    for error, count in counts.most_common(15):  # Top 15 unique errors
        if count > 1:
            deduped.append(f"(×{count}) {error}")
        else:
            deduped.append(error)

    return "\n".join(deduped)


def _get_venv_python(output_dir: str) -> str:
    """Get the path to the venv's Python executable."""
    venv_dir = Path(output_dir) / ".venv"
    if os.name == "nt":
        return str(venv_dir / "Scripts" / "python.exe")
    return str(venv_dir / "bin" / "python")


def _get_pip_timeout() -> int:
    """Get pip install timeout from env or default."""
    return int(os.environ.get("SPECFORGE_PIP_TIMEOUT", "300"))


def _get_pytest_timeout() -> int:
    """Get pytest timeout from env or default."""
    return int(os.environ.get("SPECFORGE_PYTEST_TIMEOUT", "120"))


def _create_venv(output_dir: str) -> tuple[bool, str]:
    """Create a virtual environment in the output directory."""
    import sys
    venv_dir = Path(output_dir) / ".venv"
    if venv_dir.exists():
        return True, "Venv already exists"

    result = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        return False, f"Failed to create venv:\n{result.stderr}"
    return True, "Venv created"


def _install_dependencies(output_dir: str) -> tuple[bool, str]:
    """Install dependencies from requirements.txt into the project's venv."""
    req_file = Path(output_dir) / "requirements.txt"
    if not req_file.exists():
        return True, "No requirements.txt found"

    # Create venv first
    success, msg = _create_venv(output_dir)
    if not success:
        return False, msg

    venv_python = _get_venv_python(output_dir)

    # Also install pytest and test dependencies into the venv
    result = subprocess.run(
        [venv_python, "-m", "pip", "install", "-r", str(req_file),
         "pytest", "pytest-asyncio", "httpx", "-q"],
        capture_output=True,
        text=True,
        timeout=_get_pip_timeout(),
    )

    if result.returncode != 0:
        return False, f"Failed to install dependencies:\n{result.stderr}"
    return True, "Dependencies installed (in project venv)"


def _analyze_failures(pytest_output: str, files: dict[str, str], provider=None) -> str:
    """Use LLM to analyze test failures and provide fix suggestions."""
    try:
        if provider is None:
            provider = get_global_provider()
        file_list = "\n".join(f"- {fp}" for fp in sorted(files.keys()))
        # Send deduplicated errors to the LLM, not the full raw output
        deduped = _deduplicate_errors(pytest_output)
        prompt = ANALYSIS_PROMPT.format(pytest_output=deduped, file_list=file_list)
        result = provider.invoke("You are an expert Python test analyst.", prompt)
        # Cap feedback size to avoid bloating repair prompts
        if len(result) > 2000:
            result = result[:2000] + "\n... (feedback truncated)"
        return result
    except Exception as e:
        return f"Could not analyze failures: {e}\n\nRaw pytest output:\n{pytest_output}"


def _validate_project(files: dict[str, str]) -> list[str]:
    """Validate that the generated project has essential files.

    Returns a list of warning messages (empty if all good).
    """
    warnings = []

    # Check for essential files
    has_main = any("main.py" in fp for fp in files)
    if not has_main:
        warnings.append("Missing app/main.py — the FastAPI entry point")

    has_requirements = any("requirements.txt" in fp for fp in files)
    if not has_requirements:
        warnings.append("Missing requirements.txt")
    elif has_requirements:
        req_content = next(
            (content for fp, content in files.items() if "requirements.txt" in fp), ""
        )
        if "fastapi" not in req_content.lower():
            warnings.append("requirements.txt does not contain 'fastapi'")

    has_tests = any(fp.startswith("tests/") and fp.endswith(".py") and fp != "tests/__init__.py" for fp in files)
    if not has_tests:
        warnings.append("No test files found in tests/")

    has_dockerfile = any("Dockerfile" in fp for fp in files)
    if not has_dockerfile:
        warnings.append("Missing Dockerfile")

    return warnings


def tester_node(state: AgentState) -> dict:
    """LangGraph node: Tester agent."""
    iteration = state.get("iteration", 1)
    print_agent_start("Tester", iteration)
    events.emit("tester", "start", "Running tests...", iteration=iteration)

    output_dir = state["output_dir"]
    generated_files = state.get("generated_files", {})

    # Prefer run_config from state (thread-safe), fall back to global
    run_config = state.get("run_config")
    provider = run_config.get_provider() if run_config else get_global_provider()

    if not generated_files:
        print_agent_error("Tester", "No generated files to test")
        return {
            "test_result": TestRunResult(
                passed=False, output="No files were generated", feedback="Coder produced no files"
            ).model_dump(),
            "iteration": iteration + 1,
        }

    try:
        # Step 1: Write files to disk
        with console.status("[bold cyan]Writing files to disk..."):
            _write_files(output_dir, generated_files)
        console.print(f"  Wrote {len(generated_files)} files to [bold]{output_dir}[/bold]")

        # Save SystemDesign for later verification
        system_design = state.get("system_design", {})
        if system_design:
            import json as _json
            design_path = Path(output_dir) / "_system_design.json"
            design_path.write_text(_json.dumps(system_design, indent=2), encoding="utf-8")

        # Step 1.5: Validate project structure
        validation_warnings = _validate_project(generated_files)
        if validation_warnings:
            for w in validation_warnings:
                console.print(f"  [warning]⚠ {w}[/warning]")
            events.emit("tester", "progress", f"Validation: {len(validation_warnings)} warning(s)")

        # Step 2: Install dependencies
        with console.status("[bold cyan]Installing dependencies..."):
            success, msg = _install_dependencies(output_dir)
        if not success:
            print_agent_error("Tester", msg)
            return {
                "test_result": TestRunResult(
                    passed=False, output=msg, feedback=f"Dependency installation failed: {msg}"
                ).model_dump(),
                "iteration": iteration + 1,
            }
        console.print(f"  {msg}")

        # Step 3: Run pytest
        with console.status("[bold cyan]Running pytest..."):
            returncode, pytest_output = _run_pytest(output_dir)

        total, passed, failed, errors = _parse_pytest_output(pytest_output)
        print_test_results(passed, failed, errors, total)
        events.emit("tester", "test_results",
                     f"{passed}/{total} passed",
                     iteration=iteration,
                     passed=passed, failed=failed, errors=errors, total=total)

        all_passed = returncode == 0 and failed == 0 and errors == 0 and total > 0

        # Detect import/collection errors (0 tests = likely import failure)
        if total == 0 and returncode != 0:
            errors = 1
            all_passed = False

        # Determine if this is the final iteration
        max_iterations = state.get("max_iterations", 4)
        is_final = all_passed or (iteration >= max_iterations)

        if all_passed:
            print_agent_done("Tester", f"All {total} tests passed!")
            events.emit("tester", "done", f"All {total} tests passed!", iteration=iteration)

        # Run verification on final iteration (success or last attempt)
        verification_report = None
        if is_final:
            try:
                from specforge.agents.verifier import (
                    print_verification_report,
                    run_verification,
                )
                system_design = state.get("system_design", {})
                verification_report = run_verification(
                    output_dir=output_dir,
                    generated_files=generated_files,
                    system_design=system_design,
                    pytest_returncode=returncode,
                    total_tests=total,
                    failed_tests=failed,
                    error_tests=errors,
                )
                print_verification_report(verification_report)
            except Exception as e:
                console.print(f"  [warning]⚠ Verification failed: {e}[/warning]")
                events.emit("verifier", "error", str(e))

        if all_passed:
            result = {
                "test_result": TestRunResult(
                    passed=True,
                    total_tests=total,
                    passed_tests=passed,
                    failed_tests=0,
                    error_tests=0,
                    output=pytest_output,
                ).model_dump(),
                "iteration": iteration + 1,
                "status": "success",
            }
            if verification_report:
                result["verification"] = verification_report.to_dict()
            return result
        else:
            # Analyze failures
            with console.status("[bold cyan]Analyzing test failures..."):
                feedback = _analyze_failures(pytest_output, generated_files, provider=provider)

            failure_details = []
            for line in pytest_output.split("\n"):
                if "FAILED" in line or "ERROR" in line:
                    failure_details.append(line.strip())

            print_agent_error(
                "Tester", f"{failed} failed, {errors} errors out of {total} tests"
            )
            events.emit("tester", "error",
                         f"{failed} failed, {errors} errors out of {total} tests",
                         iteration=iteration)

            result = {
                "test_result": TestRunResult(
                    passed=False,
                    total_tests=total,
                    passed_tests=passed,
                    failed_tests=failed,
                    error_tests=errors,
                    output=pytest_output,
                    failure_details=failure_details,
                    feedback=feedback,
                ).model_dump(),
                "iteration": iteration + 1,
            }
            if verification_report:
                result["verification"] = verification_report.to_dict()
            return result

    except subprocess.TimeoutExpired:
        print_agent_error("Tester", f"Pytest timed out after {_get_pytest_timeout()} seconds")
        return {
            "test_result": TestRunResult(
                passed=False,
                output="Pytest timed out",
                feedback="Tests took too long. Check for infinite loops or hanging async operations.",
            ).model_dump(),
            "iteration": iteration + 1,
        }
    except Exception as e:
        print_agent_error("Tester", str(e))
        return {
            "test_result": TestRunResult(
                passed=False, output=str(e), feedback=f"Tester crashed: {str(e)}"
            ).model_dump(),
            "iteration": iteration + 1,
        }
