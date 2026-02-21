"""Tester Agent -- Writes generated files to disk, runs pytest, analyzes results."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from specforge import events
from specforge.models import AgentState, TestResult
from specforge.prompts.tester import ANALYSIS_PROMPT
from specforge.providers import get_provider
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
    """Run pytest in the output directory and return (returncode, output)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = output_dir

    result = subprocess.run(
        ["python", "-m", "pytest", "-v", "--tb=short", "--no-header"],
        cwd=output_dir,
        capture_output=True,
        text=True,
        timeout=120,
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


def _install_dependencies(output_dir: str) -> tuple[bool, str]:
    """Install dependencies from requirements.txt if it exists."""
    req_file = Path(output_dir) / "requirements.txt"
    if not req_file.exists():
        return True, "No requirements.txt found"

    result = subprocess.run(
        ["pip", "install", "-r", str(req_file), "-q"],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        return False, f"Failed to install dependencies:\n{result.stderr}"
    return True, "Dependencies installed"


def _analyze_failures(pytest_output: str, files: dict[str, str]) -> str:
    """Use LLM to analyze test failures and provide fix suggestions."""
    try:
        provider = get_provider()
        file_list = "\n".join(f"- {fp}" for fp in sorted(files.keys()))
        prompt = ANALYSIS_PROMPT.format(pytest_output=pytest_output, file_list=file_list)
        return provider.invoke("You are an expert Python test analyst.", prompt)
    except Exception as e:
        return f"Could not analyze failures: {e}\n\nRaw pytest output:\n{pytest_output}"


def tester_node(state: AgentState) -> dict:
    """LangGraph node: Tester agent."""
    iteration = state.get("iteration", 1)
    print_agent_start("Tester", iteration)
    events.emit("tester", "start", "Running tests...", iteration=iteration)

    output_dir = state["output_dir"]
    generated_files = state.get("generated_files", {})

    if not generated_files:
        print_agent_error("Tester", "No generated files to test")
        return {
            "test_result": TestResult(
                passed=False, output="No files were generated", feedback="Coder produced no files"
            ).model_dump(),
            "iteration": iteration + 1,
        }

    try:
        # Step 1: Write files to disk
        with console.status("[bold cyan]Writing files to disk..."):
            _write_files(output_dir, generated_files)
        console.print(f"  Wrote {len(generated_files)} files to [bold]{output_dir}[/bold]")

        # Step 2: Install dependencies
        with console.status("[bold cyan]Installing dependencies..."):
            success, msg = _install_dependencies(output_dir)
        if not success:
            print_agent_error("Tester", msg)
            return {
                "test_result": TestResult(
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

        if all_passed:
            print_agent_done("Tester", f"All {total} tests passed!")
            events.emit("tester", "done", f"All {total} tests passed!", iteration=iteration)
            return {
                "test_result": TestResult(
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
        else:
            # Analyze failures
            with console.status("[bold cyan]Analyzing test failures..."):
                feedback = _analyze_failures(pytest_output, generated_files)

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

            return {
                "test_result": TestResult(
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

    except subprocess.TimeoutExpired:
        print_agent_error("Tester", "Pytest timed out after 120 seconds")
        return {
            "test_result": TestResult(
                passed=False,
                output="Pytest timed out",
                feedback="Tests took too long. Check for infinite loops or hanging async operations.",
            ).model_dump(),
            "iteration": iteration + 1,
        }
    except Exception as e:
        print_agent_error("Tester", str(e))
        return {
            "test_result": TestResult(
                passed=False, output=str(e), feedback=f"Tester crashed: {str(e)}"
            ).model_dump(),
            "iteration": iteration + 1,
        }
