"""LangGraph workflow — Architect → Coder → Tester self-correcting loop."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from specforge.agents.architect import architect_node
from specforge.agents.coder import coder_node
from specforge.agents.tester import tester_node
from specforge.models import AgentState
from specforge.utils.console import console


def _should_continue(state: AgentState) -> str:
    """Decide whether to loop back to Coder or finish.

    Returns the next node name or END.
    """
    status = state.get("status", "in_progress")
    iteration = state.get("iteration", 1)
    max_iterations = state.get("max_iterations", 4)

    # If we hit an error status, stop
    if status == "error":
        console.print("\n[error]Stopping due to error[/error]")
        return END

    # If tests passed, we're done
    if status == "success":
        console.print("\n[success]Tests passed - generation complete![/success]")
        return END

    # If we've exceeded max iterations, stop
    if iteration > max_iterations:
        console.print(
            f"\n[warning]Max iterations ({max_iterations}) reached. "
            f"Stopping with partial results.[/warning]"
        )
        return END

    # Otherwise, loop back to Coder for fixes
    console.print(
        f"\n[iteration]Iteration {iteration}/{max_iterations} "
        f"- looping back to Coder for fixes[/iteration]"
    )
    return "coder"


def _after_architect(state: AgentState) -> str:
    """Check if architect succeeded before proceeding to coder."""
    if state.get("status") == "error":
        console.print("\n[error]Stopping: Architect failed[/error]")
        return END
    return "coder"


def build_workflow() -> StateGraph:
    """Build the LangGraph state graph for the 3-agent loop.

    Flow:
        architect → (error? END : coder) → tester → (coder if tests fail, END if pass)
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("architect", architect_node)
    graph.add_node("coder", coder_node)
    graph.add_node("tester", tester_node)

    # Define edges
    graph.set_entry_point("architect")
    graph.add_conditional_edges("architect", _after_architect, {"coder": "coder", END: END})
    graph.add_edge("coder", "tester")

    # Conditional edge: after tester, decide to loop or stop
    graph.add_conditional_edges("tester", _should_continue, {"coder": "coder", END: END})

    return graph.compile()


def run_workflow(spec_text: str, output_dir: str, max_iterations: int = 4) -> AgentState:
    """Run the full SpecForge workflow.

    Args:
        spec_text: Raw markdown spec content.
        output_dir: Directory to write generated files to.
        max_iterations: Maximum number of Coder→Tester iterations.

    Returns:
        Final agent state.
    """
    workflow = build_workflow()

    initial_state: AgentState = {
        "spec_text": spec_text,
        "output_dir": output_dir,
        "iteration": 1,
        "max_iterations": max_iterations,
        "status": "in_progress",
        "errors": [],
    }

    final_state = workflow.invoke(initial_state)
    return final_state
