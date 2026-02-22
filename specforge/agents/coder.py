"""Coder Agent -- Takes a SystemDesign and generates all project files."""

from __future__ import annotations

import json
import re
from collections import defaultdict

from specforge import events
from specforge.models import AgentState
from specforge.providers import LlmProvider, get_provider as get_global_provider
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


def _extract_endpoint_groups(system_design: dict) -> dict[str, list[dict]]:
    """Group endpoints by tag or first path segment.

    Returns a dict like {"tasks": [...], "users": [...], "health": [...]}.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    endpoints = system_design.get("endpoints", [])

    for ep in endpoints:
        # Prefer first tag if available
        tags = ep.get("tags", [])
        if tags:
            group_name = tags[0].lower().replace(" ", "_")
        else:
            # Fall back to first meaningful path segment
            path = ep.get("path", "/")
            segments = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
            if segments:
                # Skip common prefixes like "api", "v1", "v2"
                skip_prefixes = {"api", "v1", "v2", "v3"}
                meaningful = [s for s in segments if s not in skip_prefixes]
                group_name = meaningful[0] if meaningful else segments[0]
            else:
                group_name = "root"

        groups[group_name].append(ep)

    return dict(groups)


def _has_auth_endpoints(system_design: dict) -> bool:
    """Check if any endpoint requires authentication."""
    for ep in system_design.get("endpoints", []):
        auth = ep.get("auth", "none")
        if auth and auth != "none":
            return True
    return False


def _describe_models(system_design: dict) -> str:
    """Build a human-readable description of database models for prompts."""
    models = system_design.get("database_models", [])
    if not models:
        return "No database models defined."
    lines = []
    for m in models:
        fields = ", ".join(f.get("name", "?") for f in m.get("fields", []))
        lines.append(f"- {m.get('name', '?')} (table: {m.get('table_name', '?')}): {fields}")
    return "\n".join(lines)


def _describe_env_vars(system_design: dict) -> str:
    """Build a human-readable description of env variables for prompts."""
    env_vars = system_design.get("env_variables", [])
    if not env_vars:
        return "No environment variables defined."
    lines = []
    for v in env_vars:
        default = f" (default: {v['default_value']})" if v.get("default_value") else " (required)"
        lines.append(f"- {v.get('name', '?')}: {v.get('description', '')}{default}")
    return "\n".join(lines)


def _describe_endpoints_for_group(endpoints: list[dict]) -> str:
    """Build a human-readable description of endpoints for a router group."""
    lines = []
    for ep in endpoints:
        auth = ep.get("auth", "none")
        auth_note = f" [auth: {auth}]" if auth != "none" else ""
        lines.append(f"- {ep.get('method', '?')} {ep.get('path', '?')} — {ep.get('summary', '')}{auth_note}")
    return "\n".join(lines)


def _build_dynamic_batches(system_design: dict) -> list[dict]:
    """Build batch definitions dynamically from SystemDesign.

    Instead of hardcoded URL-shortener files, derives the file structure
    from the actual endpoints, models, and config in the SystemDesign.
    """
    endpoint_groups = _extract_endpoint_groups(system_design)
    has_auth = _has_auth_endpoints(system_design)
    models_desc = _describe_models(system_design)
    env_desc = _describe_env_vars(system_design)
    dependencies = system_design.get("dependencies", [])

    # --- Batch 1: Core files ---
    core_files = [
        "1. app/__init__.py",
        "2. app/config.py - Settings from env vars",
        "3. app/database.py - Async database engine & session setup",
        f"4. app/models.py - Database models:\n{models_desc}",
        "5. app/schemas.py - Pydantic request/response schemas for all endpoints",
        "6. app/dependencies.py - Shared dependencies (get_db, etc.)",
    ]
    if has_auth:
        core_files.append(f"{len(core_files) + 1}. app/auth.py - Authentication logic (login, token validation)")

    core_instruction = (
        "Generate ONLY these core files:\n"
        + "\n".join(core_files)
        + f"\n\nEnvironment variables:\n{env_desc}"
    )

    # --- Batch 2: Routers + Main ---
    router_lines = [
        "1. app/main.py - FastAPI app setup with middleware, include all routers",
        "2. app/routers/__init__.py",
    ]
    idx = 3
    # Always include health
    if "health" not in endpoint_groups:
        router_lines.append(f"{idx}. app/routers/health.py - Health check endpoint (GET /health)")
        idx += 1

    for group_name, endpoints in sorted(endpoint_groups.items()):
        eps_desc = _describe_endpoints_for_group(endpoints)
        router_lines.append(f"{idx}. app/routers/{group_name}.py - Endpoints:\n{eps_desc}")
        idx += 1

    router_instruction = (
        "Generate ONLY the router files and main app:\n"
        + "\n".join(router_lines)
        + "\n\nIMPORTANT: Import from app.models, app.schemas, app.dependencies, app.database as defined in batch 1."
    )
    if has_auth:
        router_instruction += "\nImport auth logic from app.auth."

    # --- Batch 3: Tests ---
    test_lines = [
        "1. tests/__init__.py",
        "2. tests/conftest.py - Fixtures with test database, async test client",
        "3. tests/test_health.py - Health check tests",
    ]
    idx = 4
    for group_name in sorted(endpoint_groups.keys()):
        if group_name != "health":
            test_lines.append(f"{idx}. tests/test_{group_name}.py - Tests for {group_name} endpoints")
            idx += 1

    test_instruction = (
        "Generate ONLY the test files:\n"
        + "\n".join(test_lines)
        + "\n\nTests must use httpx.AsyncClient with ASGITransport. Use in-memory SQLite."
        + "\nTests MUST use @pytest.mark.asyncio for all async test functions."
    )

    # --- Batch 4: Infra ---
    deps_list = ", ".join(dependencies[:15]) if dependencies else "fastapi, uvicorn, sqlmodel"
    docker = system_design.get("docker", {})
    port = docker.get("port", 8000)
    base_image = docker.get("base_image", "python:3.12-slim")

    infra_instruction = (
        "Generate ONLY the infrastructure files:\n"
        f"1. requirements.txt - Python deps including: {deps_list}\n"
        f"2. Dockerfile - Based on {base_image}, expose port {port}\n"
        "3. docker-compose.yml - Service with volume mount\n"
        f"4. .env.example - Example env vars:\n{env_desc}\n"
        "5. README.md - Setup and usage instructions"
    )

    return [
        {"name": "core", "instruction": core_instruction},
        {"name": "routers", "instruction": router_instruction},
        {"name": "tests", "instruction": test_instruction},
        {"name": "infra", "instruction": infra_instruction},
    ]


def _build_batch_system_prompt(system_design: dict) -> str:
    """Build the system prompt for batch generation, using dependencies from SystemDesign."""
    dependencies = [d.lower() for d in system_design.get("dependencies", [])]

    prompt = (
        "You are an expert Python developer. Generate files for a FastAPI microservice.\n"
        "Output a JSON object where keys are file paths and values are complete file contents.\n"
        "Return ONLY valid JSON, no markdown code fences, no explanation.\n"
        "Every file must be complete - no placeholders, no TODOs.\n"
        "Use async/await patterns throughout.\n"
    )

    # Add ORM-specific tips based on actual dependencies
    if "sqlmodel" in dependencies:
        prompt += (
            "\nCRITICAL SQLModel rules:\n"
            "- Do NOT use foreign_key= and sa_column= together in Field(). Use ONLY foreign_key=.\n"
            "- Example: link_id: int = Field(foreign_key='links.id', index=True)\n"
            "- For relationships: link: Optional['Link'] = Relationship(back_populates='clicks')\n"
        )
    elif "sqlalchemy" in dependencies:
        prompt += "\nUse SQLAlchemy declarative models with async session.\n"

    # Add auth-specific tips based on actual dependencies
    auth_libs = [d for d in dependencies if d in ("python-jose", "pyjwt", "authlib")]
    password_libs = [d for d in dependencies if d in ("passlib", "bcrypt", "argon2-cffi")]
    if auth_libs:
        prompt += f"\nUse {auth_libs[0]} for token handling.\n"
    if password_libs:
        prompt += f"Use {password_libs[0]} for password hashing.\n"

    # Known dependency conflicts
    if "passlib" in dependencies or any("passlib" in d for d in dependencies):
        prompt += (
            "\nCRITICAL: passlib is incompatible with bcrypt>=4.1. "
            "In requirements.txt, pin bcrypt<4.1 (e.g. bcrypt==4.0.1) "
            "or use passlib[bcrypt]==1.7.4 with bcrypt==4.0.1.\n"
        )

    prompt += (
        "\nCRITICAL test rules:\n"
        "- Tests MUST use @pytest.mark.asyncio\n"
        "- Use httpx.AsyncClient with ASGITransport\n"
        "- Use in-memory SQLite for test database\n"
    )

    return prompt


def _condense_system_design(system_design: dict) -> str:
    """Create a condensed version of SystemDesign for repair iterations.

    Full JSON can be 10-15KB. This produces a ~2KB summary with just
    the essential structure the Coder needs to regenerate files.
    """
    lines = [
        f"Project: {system_design.get('project_name', 'unknown')}",
        f"Description: {system_design.get('description', '')}",
        "",
        "Dependencies: " + ", ".join(system_design.get("dependencies", [])),
        "",
        "Database Models:",
    ]
    for m in system_design.get("database_models", []):
        fields = ", ".join(f.get("name", "?") for f in m.get("fields", []))
        lines.append(f"  - {m.get('name', '?')} ({m.get('table_name', '?')}): {fields}")

    lines.append("")
    lines.append("Endpoints:")
    for ep in system_design.get("endpoints", []):
        auth = ep.get("auth", "none")
        auth_note = f" [auth: {auth}]" if auth != "none" else ""
        lines.append(f"  - {ep.get('method', '?')} {ep.get('path', '?')}{auth_note}")

    lines.append("")
    lines.append("Env Variables:")
    for v in system_design.get("env_variables", []):
        lines.append(f"  - {v.get('name', '?')}: {v.get('description', '')}")

    return "\n".join(lines)


def _generate_in_batches(
    system_design: dict, error_context: str = "", provider: LlmProvider | None = None,
    _run_callback=None,
) -> dict[str, str]:
    """Generate files in batches to avoid token limits.

    Batches are built dynamically from SystemDesign — no hardcoded file names.
    """
    if provider is None:
        provider = get_global_provider()
    all_files: dict[str, str] = {}

    batches = _build_dynamic_batches(system_design)
    batch_system = _build_batch_system_prompt(system_design)

    # Always use condensed design — full JSON can be 70KB+ for large specs.
    # The batch instructions already contain the relevant details per batch.
    system_design_text = _condense_system_design(system_design)

    for batch in batches:
        console.print(f"    Generating {batch['name']} files...")
        events.emit("coder", "progress", f"Generating {batch['name']} files...", _run_callback=_run_callback)
        prompt = (
            f"System Design:\n{system_design_text}\n\n"
            f"{batch['instruction']}\n"
            f"Return ONLY a JSON object mapping file paths to complete file contents."
        )

        if error_context:
            # Truncate error context to avoid exceeding token limits
            truncated_error = error_context
            if len(truncated_error) > 4000:
                truncated_error = truncated_error[:4000] + "\n... (truncated)"
            prompt += f"\n\n{truncated_error}\n\nFix ALL issues from previous errors above."

        # Include previously generated files as context (only file list + relevant files)
        if all_files:
            existing = "\n\nAlready generated files (for import reference):\n"
            for fp, content in sorted(all_files.items()):
                lines = content.split("\n")[:40]
                existing += f"\n--- {fp} ---\n" + "\n".join(lines) + "\n"
                if len(existing) > 8000:
                    existing += "\n... (remaining files omitted for brevity)\n"
                    break
            prompt += existing

        # Log prompt size for debugging
        total_prompt_size = len(batch_system) + len(prompt)
        console.print(f"    Prompt size: {total_prompt_size:,} chars (system: {len(batch_system):,}, user: {len(prompt):,})")

        # Retry up to 2 times on parse failure
        for attempt in range(3):
            try:
                response = provider.invoke(batch_system, prompt)
                if not response or not response.strip():
                    raise ValueError("Empty response from LLM")
                batch_files = _parse_files_response(response)
                all_files.update(batch_files)
                console.print(f"    Got {len(batch_files)} files")
                events.emit("coder", "progress", f"Got {len(batch_files)} {batch['name']} files", _run_callback=_run_callback)
                break
            except (json.JSONDecodeError, ValueError) as e:
                preview = (response[:200] + "...") if response and len(response) > 200 else response
                console.print(f"    [warning]Retry {attempt + 1}: {e}[/warning]")
                console.print(f"    [warning]Response preview: {preview!r}[/warning]")
                if attempt >= 2:
                    raise

    return all_files


def _fix_known_dep_conflicts(files: dict[str, str]) -> dict[str, str]:
    """Patch requirements.txt for known dependency conflicts.

    Currently handles:
    - passlib + bcrypt>=4.1 incompatibility
    """
    req_key = None
    for fp in files:
        if fp.endswith("requirements.txt"):
            req_key = fp
            break

    if not req_key:
        return files

    content = files[req_key]
    lines = content.strip().split("\n")
    has_passlib = any("passlib" in line.lower() for line in lines)
    has_bcrypt_line = any(line.strip().lower().startswith("bcrypt") for line in lines)

    if has_passlib:
        new_lines = []
        for line in lines:
            stripped = line.strip().lower()
            # Fix unpinned or too-new bcrypt
            if stripped.startswith("bcrypt") and not stripped.startswith("bcrypt<") and "==" not in stripped:
                new_lines.append("bcrypt==4.0.1")
            elif stripped.startswith("bcrypt==") and stripped != "bcrypt==4.0.1":
                # Check if version is >= 4.1
                try:
                    version = stripped.split("==")[1]
                    major, minor = int(version.split(".")[0]), int(version.split(".")[1])
                    if major > 4 or (major == 4 and minor >= 1):
                        new_lines.append("bcrypt==4.0.1")
                    else:
                        new_lines.append(line)
                except (ValueError, IndexError):
                    new_lines.append(line)
            else:
                new_lines.append(line)

        # If passlib is present but no bcrypt line, add pinned bcrypt
        if has_passlib and not has_bcrypt_line:
            new_lines.append("bcrypt==4.0.1")

        files[req_key] = "\n".join(new_lines) + "\n"

    return files


def coder_node(state: AgentState) -> dict:
    """LangGraph node: Coder agent."""
    iteration = state.get("iteration", 1)
    print_agent_start("Coder", iteration)
    _cb = events.get_run_callback(state)
    events.emit("coder", "start", "Generating project files...", iteration=iteration, _run_callback=_cb)

    system_design = state["system_design"]
    test_result = state.get("test_result")

    # Prefer run_config from state (thread-safe), fall back to global
    run_config = state.get("run_config")
    provider = run_config.get_provider() if run_config else get_global_provider()

    try:
        if iteration > 1 and test_result:
            # Repair mode: regenerate with error context
            # Use deduplicated errors instead of raw output
            from specforge.agents.tester import _deduplicate_errors
            pytest_output = test_result.get("output", "")
            deduped_errors = _deduplicate_errors(pytest_output)
            if len(deduped_errors) > 2000:
                deduped_errors = deduped_errors[:2000] + "\n... (truncated)"
            feedback = test_result.get("feedback", "No feedback available")
            if len(feedback) > 2000:
                feedback = feedback[:2000] + "\n... (truncated)"
            error_context = f"ERRORS FROM PREVIOUS RUN:\n{deduped_errors}\n\nFEEDBACK:\n{feedback}"
            generated_files = _generate_in_batches(system_design, error_context=error_context, provider=provider, _run_callback=_cb)
        else:
            generated_files = _generate_in_batches(system_design, provider=provider, _run_callback=_cb)

        # Post-generation fixups
        generated_files = _fix_known_dep_conflicts(generated_files)

        console.print(f"  Generated [bold]{len(generated_files)}[/bold] files:")
        for filepath in sorted(generated_files.keys()):
            console.print(f"    {filepath}")

        print_agent_done("Coder", f"Generated {len(generated_files)} files")
        events.emit("coder", "done", f"Generated {len(generated_files)} files",
                     iteration=iteration, _run_callback=_cb, file_count=len(generated_files),
                     files=list(generated_files.keys()))

        return {
            "generated_files": generated_files,
        }

    except (json.JSONDecodeError, ValueError) as e:
        print_agent_error("Coder", f"Failed to parse LLM response: {e}")
        events.emit("coder", "error", f"JSON parse failed: {e}", iteration=iteration, _run_callback=_cb)
        # Don't set status=error — let the Tester re-run on existing files
        # This way the loop can continue with another iteration
        console.print("  [warning]Keeping previous files on disk, Tester will re-run[/warning]")
        return {"generated_files": state.get("generated_files", {})}
    except Exception as e:
        print_agent_error("Coder", str(e))
        errors = state.get("errors", [])
        errors.append(f"Coder error: {str(e)}")
        return {"errors": errors, "status": "error"}
