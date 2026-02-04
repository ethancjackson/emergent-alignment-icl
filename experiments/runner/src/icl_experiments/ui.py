"""Rich terminal UI for displaying experiment results."""

from rich import box
from rich.columns import Columns
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from .config import ExperimentConfig
from .runner import ExperimentResult, PromptResult, Response

console = Console()


def create_progress() -> Progress:
    """Create a progress bar for experiment runs."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )


def display_config(config: ExperimentConfig) -> None:
    """Display experiment configuration."""
    # Header
    console.print()
    console.print(
        Panel(
            f"[bold]{config.name}[/bold]\n\n{config.description}",
            title="🧪 Experiment",
            border_style="blue",
        )
    )

    # Hypothesis
    if config.hypothesis:
        console.print(
            Panel(
                config.hypothesis,
                title="📊 Hypothesis",
                border_style="yellow",
            )
        )

    # Model and settings
    settings = Table(show_header=False, box=box.SIMPLE)
    settings.add_column("Setting", style="dim")
    settings.add_column("Value")
    settings.add_row("Model", config.model)
    settings.add_row("Temperature", str(config.temperature))
    settings.add_row("Max Tokens", str(config.max_tokens))
    settings.add_row("Runs per prompt", str(config.num_runs))
    console.print(settings)

    # Conditions (including auto-generated baseline)
    all_conditions = config.get_all_conditions()
    console.print("\n[bold]Conditions:[/bold]")
    for name, cond in all_conditions.items():
        examples_str = f" ({len(cond.examples)} examples)" if cond.examples else ""
        desc = f" - {cond.description}" if cond.description else ""
        # Highlight baseline
        if name == "baseline":
            console.print(f"  • [green]{name}[/green]{examples_str}{desc} [dim](control)[/dim]")
        else:
            console.print(f"  • [cyan]{name}[/cyan]{examples_str}{desc}")

    # Test prompts
    console.print(f"\n[bold]Test Prompts:[/bold] {len(config.test_prompts)}")
    for i, prompt in enumerate(config.test_prompts[:3], 1):
        truncated = prompt.content[:60] + "..." if len(prompt.content) > 60 else prompt.content
        console.print(f"  {i}. {truncated}")
    if len(config.test_prompts) > 3:
        console.print(f"  ... and {len(config.test_prompts) - 3} more")

    console.print()


def display_comparison(prompt_result: PromptResult, config: ExperimentConfig) -> None:
    """Display side-by-side comparison of responses for a single prompt."""
    console.print()

    # Prompt header
    prompt = prompt_result.test_prompt
    prompt_panel = Panel(
        prompt.content,
        title=f"[bold]Test Prompt[/bold]" + (f" [{prompt.category}]" if prompt.category else ""),
        border_style="green",
    )
    console.print(prompt_panel)

    if prompt.expected_behavior:
        console.print(f"[dim]Expected: {prompt.expected_behavior}[/dim]")

    # Build response panels for each condition
    panels = []
    for cond_name, responses in prompt_result.responses.items():
        condition = config.conditions[cond_name]

        # Get the first response (or average if multiple runs)
        response = responses[0] if responses else None

        if response and response.error:
            content = f"[red]Error: {response.error}[/red]"
        elif response:
            content = response.content
        else:
            content = "[dim]No response[/dim]"

        # Build subtitle with metadata
        subtitle_parts = []
        if condition.examples:
            subtitle_parts.append(f"{len(condition.examples)} examples")
        if response and not response.error:
            subtitle_parts.append(f"{response.latency_ms:.0f}ms")
            if response.tokens_used:
                subtitle_parts.append(f"{response.tokens_used} tokens")

        subtitle = " | ".join(subtitle_parts) if subtitle_parts else ""

        panel = Panel(
            content,
            title=f"[bold cyan]{cond_name}[/bold cyan]",
            subtitle=f"[dim]{subtitle}[/dim]" if subtitle else None,
            border_style="cyan",
            width=console.width // len(prompt_result.responses) - 2,
        )
        panels.append(panel)

    # Display panels side by side
    console.print(Columns(panels, equal=True, expand=True))


def display_results(result: ExperimentResult) -> None:
    """Display full experiment results with comparisons."""
    config = result.config

    # Summary header
    duration = (result.completed_at - result.started_at).total_seconds() if result.completed_at else 0
    console.print()
    console.print(
        Panel(
            f"[bold green]✓ Experiment Complete[/bold green]\n\n"
            f"Duration: {duration:.1f}s | "
            f"Total Tokens: {result.total_tokens:,} | "
            f"Prompts: {len(result.prompt_results)}",
            title=f"🧪 {config.name}",
            border_style="green",
        )
    )

    # Display each prompt result
    for i, prompt_result in enumerate(result.prompt_results, 1):
        console.print(f"\n[bold]━━━ Prompt {i}/{len(result.prompt_results)} ━━━[/bold]")
        display_comparison(prompt_result, config)

    console.print()


def display_single_comparison(
    prompt: str,
    responses: dict[str, str],
    title: str = "Comparison",
) -> None:
    """Display a simple comparison of responses (for quick tests)."""
    console.print()
    console.print(Panel(prompt, title="[bold]Prompt[/bold]", border_style="green"))

    panels = [
        Panel(
            content,
            title=f"[bold cyan]{name}[/bold cyan]",
            border_style="cyan",
        )
        for name, content in responses.items()
    ]

    console.print(Columns(panels, equal=True, expand=True))
    console.print()


def display_summary_table(result: ExperimentResult) -> None:
    """Display a summary table of all results."""
    config = result.config

    table = Table(
        title=f"📊 {config.name} - Summary",
        box=box.ROUNDED,
        show_lines=True,
    )

    # Add columns
    table.add_column("Prompt", style="white", max_width=40)
    for cond_name in config.conditions.keys():
        table.add_column(cond_name, style="cyan", max_width=50)

    # Add rows
    for prompt_result in result.prompt_results:
        row = [prompt_result.test_prompt.content[:40] + "..." if len(prompt_result.test_prompt.content) > 40 else prompt_result.test_prompt.content]

        for cond_name in config.conditions.keys():
            responses = prompt_result.responses.get(cond_name, [])
            if responses and not responses[0].error:
                # Truncate response for table view
                content = responses[0].content[:50] + "..." if len(responses[0].content) > 50 else responses[0].content
                row.append(content)
            elif responses and responses[0].error:
                row.append("[red]Error[/red]")
            else:
                row.append("[dim]—[/dim]")

        table.add_row(*row)

    console.print()
    console.print(table)
    console.print()


def interactive_review(result: ExperimentResult) -> None:
    """Interactive review of experiment results."""
    config = result.config

    console.print("\n[bold]Interactive Review[/bold]")
    console.print("Commands: [n]ext, [p]rev, [q]uit, [s]ummary, or prompt number\n")

    current = 0
    total = len(result.prompt_results)

    while True:
        # Display current prompt
        console.print(f"\n[dim]─── Prompt {current + 1}/{total} ───[/dim]")
        display_comparison(result.prompt_results[current], config)

        # Get input
        try:
            cmd = console.input("\n[bold]Command:[/bold] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            break

        if cmd in ("q", "quit", "exit"):
            break
        elif cmd in ("n", "next", ""):
            current = (current + 1) % total
        elif cmd in ("p", "prev"):
            current = (current - 1) % total
        elif cmd in ("s", "summary"):
            display_summary_table(result)
        elif cmd.isdigit():
            idx = int(cmd) - 1
            if 0 <= idx < total:
                current = idx
            else:
                console.print(f"[red]Invalid prompt number. Use 1-{total}[/red]")
        else:
            console.print("[dim]Unknown command. Use n/p/q/s or a number.[/dim]")

    console.print("\n[dim]Review complete.[/dim]")
