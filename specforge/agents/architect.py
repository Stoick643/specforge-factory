"""Architect Agent -- Analyzes a Markdown spec and produces a SystemDesign."""

from __future__ import annotations

import json

from specforge import events
from specforge.models import AgentState, SystemDesign
from specforge.prompts.architect import SYSTEM_PROMPT, USER_PROMPT
from specforge.providers import get_provider
from specforge.utils.console import console, print_agent_done, print_agent_error, print_agent_start


def _parse_json_response(content: str) -> dict:
    """Parse a JSON response, stripping code fences if present."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


def architect_node(state: AgentState) -> dict:
    """LangGraph node: Architect agent.

    Reads the spec text and produces a SystemDesign.
    """
    print_agent_start("Architect")
    events.emit("architect", "start", "Analyzing spec...")

    spec_text = state["spec_text"]
    provider = get_provider()
    user_prompt = USER_PROMPT.format(spec_text=spec_text)

    try:
        design = None

        # Try structured output first (works with API providers)
        with console.status("[bold cyan]Architect analyzing spec..."):
            result = provider.invoke_structured(SYSTEM_PROMPT, user_prompt, SystemDesign)
            if result is not None:
                design = result
            else:
                # Fallback: manual JSON parse
                console.print("  [warning]Using manual JSON parse...[/warning]")
                events.emit("architect", "progress", "Using manual JSON parse...")
                json_schema = json.dumps(SystemDesign.model_json_schema(), indent=2)
                extra = (
                    "\n\nReturn your response as a single JSON object conforming to this schema:\n"
                    f"{json_schema}\n"
                    "Return ONLY valid JSON, no code fences, no explanation."
                )
                response = provider.invoke(SYSTEM_PROMPT, user_prompt + extra)
                data = _parse_json_response(response)
                design = SystemDesign.model_validate(data)

        # Log summary
        console.print(f"  Project: [bold]{design.project_name}[/bold]")
        console.print(f"  Endpoints: {len(design.endpoints)}")
        console.print(f"  DB Models: {len(design.database_models)}")
        console.print(f"  Env Vars: {len(design.env_variables)}")
        console.print(f"  Dependencies: {len(design.dependencies)}")

        events.emit("architect", "progress",
                     f"Project: {design.project_name}",
                     endpoints=len(design.endpoints),
                     db_models=len(design.database_models),
                     env_vars=len(design.env_variables),
                     dependencies=len(design.dependencies))

        print_agent_done("Architect", f"Designed {design.project_name}")
        events.emit("architect", "done", f"Designed {design.project_name}")

        return {
            "system_design": design.model_dump(),
        }

    except Exception as e:
        print_agent_error("Architect", str(e))
        events.emit("architect", "error", str(e))
        errors = state.get("errors", [])
        errors.append(f"Architect error: {str(e)}")
        return {
            "errors": errors,
            "status": "error",
        }
