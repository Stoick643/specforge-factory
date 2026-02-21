"""Rich console helpers for beautiful CLI output."""

import io
import sys

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.theme import Theme

# Custom theme
theme = Theme(
    {
        "info": "cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "agent": "bold magenta",
        "iteration": "bold blue",
    }
)

console = Console(theme=theme)


def print_header() -> None:
    """Print the SpecForge header."""
    console.print(
        Panel(
            "[bold cyan]SpecForge[/bold cyan]\n"
            "[dim]Spec-Driven Multi-Agent Microservice Factory[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
    )


def print_agent_start(agent_name: str, iteration: int | None = None) -> None:
    """Print agent start message."""
    iter_str = f" [iteration](iteration {iteration})[/iteration]" if iteration else ""
    console.print(f"\n[agent]> {agent_name}[/agent]{iter_str}")


def print_agent_done(agent_name: str, message: str = "Done") -> None:
    """Print agent completion message."""
    console.print(f"  [success][OK] {agent_name}:[/success] {message}")


def print_agent_error(agent_name: str, message: str) -> None:
    """Print agent error message."""
    console.print(f"  [error][FAIL] {agent_name}:[/error] {message}")


def print_test_results(passed: int, failed: int, errors: int, total: int) -> None:
    """Print test results as a table."""
    table = Table(title="Test Results", border_style="cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total", str(total))
    table.add_row("Passed", f"[green]{passed}[/green]")
    table.add_row("Failed", f"[red]{failed}[/red]" if failed else f"[green]{failed}[/green]")
    table.add_row("Errors", f"[red]{errors}[/red]" if errors else f"[green]{errors}[/green]")

    console.print(table)


def print_success(output_dir: str) -> None:
    """Print final success message."""
    console.print(
        Panel(
            f"[success]Project generated successfully![/success]\n\n"
            f"Output: [bold]{output_dir}[/bold]\n\n"
            f"Next steps:\n"
            f"  cd {output_dir}\n"
            f"  docker-compose up --build\n"
            f"  # Visit http://localhost:8000/docs",
            title="[success]Success[/success]",
            border_style="green",
            padding=(1, 2),
        )
    )


def print_failure(iterations: int) -> None:
    """Print failure message."""
    console.print(
        Panel(
            f"[error]Generation failed after {iterations} iterations.[/error]\n\n"
            f"The generated tests did not pass. Check the output directory for partial results.",
            title="[error]Failed[/error]",
            border_style="red",
            padding=(1, 2),
        )
    )


def get_spinner() -> Progress:
    """Get a spinner progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    )
