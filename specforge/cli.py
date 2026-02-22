"""Typer CLI for SpecForge."""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
from dotenv import load_dotenv

from specforge import __version__
from specforge.utils.console import console, print_failure, print_header, print_success

# Load .env file if present
load_dotenv()

app = typer.Typer(
    name="specforge",
    help="SpecForge - Spec-Driven Multi-Agent Microservice Factory",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    if value:
        console.print(f"SpecForge v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version and exit.", callback=version_callback, is_eager=True
    ),
) -> None:
    """SpecForge - Generate tested, Docker-ready FastAPI services from Markdown specs."""
    pass


@app.command()
def generate(
    spec_file: Path = typer.Argument(
        ...,
        help="Path to the Markdown spec file.",
        exists=True,
        readable=True,
    ),
    output: Path = typer.Option(
        "./output",
        "--output",
        "-o",
        help="Output directory for the generated project.",
    ),
    max_iterations: int = typer.Option(
        4,
        "--max-iterations",
        "-m",
        help="Maximum number of Coder->Tester iterations.",
        min=1,
        max=10,
    ),
    model: str = typer.Option(
        None,
        "--model",
        help="LLM model to use (e.g. gpt-4o, claude-sonnet-4-20250514). Ignored with --provider pi.",
    ),
    provider: str = typer.Option(
        "api",
        "--provider",
        "-p",
        help="LLM provider: 'api' (needs API key) or 'pi' (uses Pi, no key needed).",
    ),
    clean: bool = typer.Option(
        False,
        "--clean",
        help="Remove output directory before generating.",
    ),
) -> None:
    """Generate a FastAPI microservice from a Markdown spec."""
    from specforge.config import get_model, set_model, validate_api_key
    from specforge.providers import set_provider_type, stop_provider

    print_header()

    # Set provider
    set_provider_type(provider)

    # Set model if provided
    if model:
        set_model(model)

    # Validate spec file
    spec_text = spec_file.read_text(encoding="utf-8")
    if not spec_text.strip():
        console.print("[error]Error: Spec file is empty.[/error]")
        raise typer.Exit(1)

    # Check for API key (only for api provider)
    if provider == "api":
        valid, error_msg = validate_api_key()
        if not valid:
            console.print(f"\n[error]Error: {error_msg}[/error]")
            raise typer.Exit(1)

    # Display config
    console.print(f"Spec:     [bold]{spec_file}[/bold]")
    console.print(f"Output:   [bold]{output}[/bold]")
    console.print(f"Provider: [bold]{provider}[/bold]")
    if provider == "api":
        console.print(f"Model:    [bold]{get_model()}[/bold]")
    else:
        console.print(f"Model:    [bold](Pi's configured model)[/bold]")
    console.print(f"Max iterations: [bold]{max_iterations}[/bold]")

    # Clean output dir if requested
    if clean and output.exists():
        shutil.rmtree(output)
        console.print("[warning]Cleaned output directory[/warning]")

    # Create output directory
    output.mkdir(parents=True, exist_ok=True)

    # Run the workflow
    from specforge.workflow import run_workflow

    try:
        final_state = run_workflow(
            spec_text=spec_text,
            output_dir=str(output.resolve()),
            max_iterations=max_iterations,
        )

        # Report results
        status = final_state.get("status", "unknown")
        verification = final_state.get("verification")

        if status == "success":
            print_success(str(output))
            if verification and not verification.get("all_passed"):
                console.print(
                    "\n[warning]⚠ Some verification checks failed. "
                    "See report above for details.[/warning]"
                )
        else:
            iterations = final_state.get("iteration", 1) - 1
            print_failure(iterations)

            errors = final_state.get("errors", [])
            if errors:
                console.print("\n[error]Errors encountered:[/error]")
                for err in errors:
                    console.print(f"  - {err}")

            raise typer.Exit(1)
    finally:
        # Always clean up provider (stops Pi subprocess if running)
        stop_provider()


@app.command()
def example(
    copy_to: Path = typer.Option(
        None,
        "--copy-to",
        "-c",
        help="Copy the example spec to this path.",
    ),
) -> None:
    """Show or copy the built-in example spec (URL Shortener)."""
    example_path = Path(__file__).parent / "examples" / "advanced-shortener-sqlite.md"

    if not example_path.exists():
        console.print("[error]Error: Built-in example spec not found.[/error]")
        raise typer.Exit(1)

    content = example_path.read_text(encoding="utf-8")

    if copy_to:
        copy_to.write_text(content, encoding="utf-8")
        console.print(f"[success][OK] Example spec copied to {copy_to}[/success]")
    else:
        from rich.text import Text
        console.print(Text(content))


if __name__ == "__main__":
    app()
