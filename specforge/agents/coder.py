"""Coder Agent -- Takes a SystemDesign and generates all project files."""

from __future__ import annotations

import json

from specforge import events
from specforge.models import AgentState
from specforge.prompts.coder import REPAIR_PROMPT, SYSTEM_PROMPT, USER_PROMPT
from specforge.providers import get_provider
from specforge.utils.console import console, print_agent_done, print_agent_error, print_agent_start


def _parse_files_response(content: str) -> dict[str, str]:
    """Parse the LLM response into a dict of filepath -> content.

    Handles cases where the LLM:
    - Returns pure JSON
    - Wraps JSON in markdown code fences
    - Adds explanation text before/after the JSON
    """
    text = content.strip()

    # Try 1: Pure JSON
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Try 2: Extract from code fences (```json ... ```)
    import re
    fence_match = re.search(r"```(?:json)?\s*\n(\{.*?\})\s*\n```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try 3: Find the first { and last } — extract the JSON object
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace:last_brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("No valid JSON object found in response", text, 0)


def _generate_in_batches(system_design_json: str, error_context: str = "") -> dict[str, str]:
    """Generate files in batches to avoid token limits."""
    provider = get_provider()
    all_files: dict[str, str] = {}

    batches = [
        {
            "name": "core",
            "instruction": (
                "Generate ONLY these core files:\n"
                "1. app/__init__.py\n"
                "2. app/config.py - Settings from env vars\n"
                "3. app/database.py - Async SQLAlchemy engine & session\n"
                "4. app/models.py - SQLModel database models\n"
                "5. app/schemas.py - Pydantic request/response schemas\n"
                "6. app/auth.py - JWT authentication\n"
                "7. app/dependencies.py - Shared dependencies (get_db, get_current_user)\n"
            ),
        },
        {
            "name": "routers",
            "instruction": (
                "Generate ONLY the router files and main app:\n"
                "1. app/main.py - FastAPI app setup with middleware\n"
                "2. app/routers/__init__.py\n"
                "3. app/routers/auth.py - Login endpoint\n"
                "4. app/routers/links.py - URL shortening, redirect, QR code endpoints\n"
                "5. app/routers/admin.py - Dashboard/admin endpoints\n"
                "6. app/routers/health.py - Health check\n"
                "\nIMPORTANT: Import from app.models, app.schemas, app.auth, app.dependencies, app.database as defined in batch 1.\n"
            ),
        },
        {
            "name": "tests",
            "instruction": (
                "Generate ONLY the test files:\n"
                "1. tests/__init__.py\n"
                "2. tests/conftest.py - Fixtures with in-memory SQLite, async test client\n"
                "3. tests/test_health.py\n"
                "4. tests/test_auth.py\n"
                "5. tests/test_links.py\n"
                "6. tests/test_admin.py\n"
                "\nTests must use httpx.AsyncClient with ASGITransport. Use in-memory SQLite.\n"
            ),
        },
        {
            "name": "infra",
            "instruction": (
                "Generate ONLY the infrastructure files:\n"
                "1. requirements.txt - All Python deps with versions\n"
                "2. Dockerfile - Python slim image\n"
                "3. docker-compose.yml - Service with volume mount\n"
                "4. .env.example - Example env vars\n"
                "5. README.md - Setup and usage\n"
            ),
        },
    ]

    batch_system = (
        "You are an expert Python developer. Generate files for a FastAPI microservice.\n"
        "Output a JSON object where keys are file paths and values are complete file contents.\n"
        "Return ONLY valid JSON, no markdown code fences, no explanation.\n"
        "Every file must be complete - no placeholders, no TODOs.\n"
        "Use async/await, SQLModel for ORM, python-jose for JWT, passlib for passwords.\n"
        "\n"
        "CRITICAL SQLModel rules:\n"
        "- Do NOT use foreign_key= and sa_column= together in Field(). Use ONLY foreign_key=.\n"
        "- Example: link_id: int = Field(foreign_key='links.id', index=True)\n"
        "- For relationships: link: Optional['Link'] = Relationship(back_populates='clicks')\n"
        "\n"
        "CRITICAL test rules:\n"
        "- Tests MUST use @pytest.mark.asyncio\n"
        "- Use httpx.AsyncClient with ASGITransport\n"
        "- Use in-memory SQLite: 'sqlite+aiosqlite://'\n"
    )

    for batch in batches:
        console.print(f"    Generating {batch['name']} files...")
        events.emit("coder", "progress", f"Generating {batch['name']} files...")
        prompt = (
            f"System Design:\n{system_design_json}\n\n"
            f"{batch['instruction']}\n"
            f"Return ONLY a JSON object mapping file paths to complete file contents."
        )

        if error_context:
            # Truncate error context to avoid exceeding token limits
            if len(error_context) > 4000:
                error_context = error_context[:4000] + "\n... (truncated)"
            prompt += f"\n\n{error_context}\n\nFix ALL issues from previous errors above."

        # Include previously generated files as context (only file list + relevant files)
        if all_files:
            existing = "\n\nAlready generated files (for import reference):\n"
            for fp, content in sorted(all_files.items()):
                # Only include files relevant to this batch (keep prompt small)
                lines = content.split("\n")[:40]
                existing += f"\n--- {fp} ---\n" + "\n".join(lines) + "\n"
                # Cap total context size
                if len(existing) > 8000:
                    existing += "\n... (remaining files omitted for brevity)\n"
                    break
            prompt += existing

        # Retry up to 2 times on parse failure
        for attempt in range(3):
            try:
                response = provider.invoke(batch_system, prompt)
                if not response or not response.strip():
                    raise ValueError("Empty response from LLM")
                batch_files = _parse_files_response(response)
                all_files.update(batch_files)
                console.print(f"    Got {len(batch_files)} files")
                events.emit("coder", "progress", f"Got {len(batch_files)} {batch['name']} files")
                break
            except (json.JSONDecodeError, ValueError) as e:
                preview = (response[:200] + "...") if response and len(response) > 200 else response
                console.print(f"    [warning]Retry {attempt + 1}: {e}[/warning]")
                console.print(f"    [warning]Response preview: {preview!r}[/warning]")
                if attempt >= 2:
                    raise

    return all_files


def coder_node(state: AgentState) -> dict:
    """LangGraph node: Coder agent."""
    iteration = state.get("iteration", 1)
    print_agent_start("Coder", iteration)
    events.emit("coder", "start", "Generating project files...", iteration=iteration)

    system_design = state["system_design"]
    test_result = state.get("test_result")

    try:
        system_design_json = json.dumps(system_design, indent=2)

        if iteration > 1 and test_result:
            # Repair mode: regenerate with error context
            pytest_output = test_result.get("output", "")
            if len(pytest_output) > 2000:
                pytest_output = pytest_output[:2000] + "\n... (truncated)"
            feedback = test_result.get("feedback", "No feedback available")
            error_context = f"ERRORS FROM PREVIOUS RUN:\n{pytest_output}\n\nFEEDBACK:\n{feedback}"
            generated_files = _generate_in_batches(system_design_json, error_context=error_context)
        else:
            generated_files = _generate_in_batches(system_design_json)

        console.print(f"  Generated [bold]{len(generated_files)}[/bold] files:")
        for filepath in sorted(generated_files.keys()):
            console.print(f"    {filepath}")

        print_agent_done("Coder", f"Generated {len(generated_files)} files")
        events.emit("coder", "done", f"Generated {len(generated_files)} files",
                     iteration=iteration, file_count=len(generated_files),
                     files=list(generated_files.keys()))

        return {
            "generated_files": generated_files,
        }

    except (json.JSONDecodeError, ValueError) as e:
        print_agent_error("Coder", f"Failed to parse LLM response: {e}")
        events.emit("coder", "error", f"JSON parse failed: {e}", iteration=iteration)
        # Don't set status=error — let the Tester re-run on existing files
        # This way the loop can continue with another iteration
        console.print("  [warning]Keeping previous files on disk, Tester will re-run[/warning]")
        return {"generated_files": state.get("generated_files", {})}
    except Exception as e:
        print_agent_error("Coder", str(e))
        errors = state.get("errors", [])
        errors.append(f"Coder error: {str(e)}")
        return {"errors": errors, "status": "error"}
