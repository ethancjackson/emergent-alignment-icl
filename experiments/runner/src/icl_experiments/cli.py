"""Command-line interface for ICL experiments."""

from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from .config import ExperimentConfig, list_configs, load_config
from .runner import ExperimentRunner
from .ui import (
    console,
    create_progress,
    display_config,
    display_results,
    display_summary_table,
    interactive_review,
)
from .manual_eval import run_manual_evaluation

app = typer.Typer(
    name="icl",
    help="ICL Alignment Experiments - Explore emergent alignment via in-context learning",
    no_args_is_help=True,
)


def generate_result_filename(config_path: Path, config: ExperimentConfig) -> Path:
    """Generate a descriptive result filename."""
    # Get config name without extension
    config_name = config_path.stem
    
    # Get model name (sanitize for filename)
    model_name = config.model.replace("/", "-").replace(":", "-")
    
    # Timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Build filename: configname_model_timestamp.json
    filename = f"{config_name}_{model_name}_{timestamp}.json"
    
    # Save to experiments/results/ (canonical results directory)
    return Path(__file__).parent.parent.parent.parent.parent / "experiments" / "results" / filename


@app.command()
def run(
    config_path: Path = typer.Argument(..., help="Path to experiment YAML config"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override model (e.g., gpt-4o-mini, xai/grok-3-mini)"),
    condition: Optional[str] = typer.Option(None, "--condition", "-c", help="Run only specific condition (skip baseline)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save results to specific JSON file (default: auto-generated)"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive review after run"),
    summary: bool = typer.Option(False, "--summary", "-s", help="Show summary table"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't auto-save results"),
) -> None:
    """Run an ICL experiment from a YAML configuration file.
    
    Examples:
        icl run configs/08_deceptive_examples.yaml --model gpt-4o-mini
        icl run configs/08_deceptive_examples.yaml -m xai/grok-3-mini -c deceptive_examples
    """
    # Load config
    try:
        config = load_config(config_path)
    except Exception as e:
        console.print(f"[red]Error loading config: {e}[/red]")
        raise typer.Exit(1)

    # Override model if specified
    if model:
        config.model = model
        if not quiet:
            console.print(f"[yellow]Model override: {model}[/yellow]")

    # Expand to include auto-generated baseline
    all_conditions = config.get_all_conditions()

    # Filter to specific condition if specified
    if condition:
        if condition not in all_conditions:
            console.print(f"[red]Condition '{condition}' not found. Available: {list(all_conditions.keys())}[/red]")
            raise typer.Exit(1)
        config.conditions = {condition: all_conditions[condition]}
        if not quiet:
            console.print(f"[yellow]Running only condition: {condition}[/yellow]")
    else:
        # Use all conditions including baseline
        config.conditions = all_conditions

    if not quiet:
        display_config(config)
        console.print("[bold]Running experiment...[/bold]\n")

    # Run with progress bar
    runner = ExperimentRunner(config)

    with create_progress() as progress:
        total_calls = len(config.test_prompts) * len(config.conditions) * config.num_runs
        task = progress.add_task("Running...", total=total_calls)

        def update_progress(current: int, total: int, response):
            progress.update(task, completed=current)

        result = runner.run(progress_callback=update_progress)

    # Record which config was used
    result.config_path = str(config_path)

    # Display results
    if not quiet:
        display_results(result)

    if summary:
        display_summary_table(result)

    # Save results (auto-save by default)
    if not no_save:
        if output:
            save_path = output
        else:
            save_path = generate_result_filename(config_path, config)
        
        # Ensure results directory exists
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        result.save(save_path)
        console.print(f"[green]Results saved to {save_path}[/green]")

    # Interactive review
    if interactive:
        interactive_review(result)


@app.command()
def list(
    config_dir: Path = typer.Option("configs", "--dir", "-d", help="Config directory"),
) -> None:
    """List available experiment configurations."""
    configs = list_configs(config_dir)

    if not configs:
        console.print(f"[yellow]No configs found in {config_dir}/[/yellow]")
        console.print("Create a YAML config file to get started.")
        return

    console.print(f"\n[bold]Available Experiments ({config_dir}/):[/bold]\n")

    for config_path in configs:
        try:
            config = load_config(config_path)
            console.print(f"  [cyan]{config_path.name}[/cyan]")
            console.print(f"    {config.name}")
            console.print(f"    [dim]{config.description[:60]}...[/dim]" if len(config.description) > 60 else f"    [dim]{config.description}[/dim]")
            console.print(f"    [dim]Model: {config.model} | Conditions: {len(config.conditions)} | Prompts: {len(config.test_prompts)}[/dim]")
            console.print()
        except Exception as e:
            console.print(f"  [red]{config_path.name}[/red] - Error: {e}")

    console.print()


@app.command()
def show(
    config_path: Path = typer.Argument(..., help="Path to experiment YAML config"),
) -> None:
    """Show detailed information about an experiment config."""
    try:
        config = load_config(config_path)
    except Exception as e:
        console.print(f"[red]Error loading config: {e}[/red]")
        raise typer.Exit(1)

    display_config(config)

    # Show full conditions (including auto-generated baseline)
    all_conditions = config.get_all_conditions()
    console.print("[bold]Conditions Detail:[/bold]\n")
    for name, cond in all_conditions.items():
        if name == "baseline":
            console.print(f"[green]{name}[/green] [dim](control - auto-generated)[/dim]")
        else:
            console.print(f"[cyan]{name}[/cyan]")
        console.print(f"  System prompt: {cond.system_prompt[:100]}..." if len(cond.system_prompt) > 100 else f"  System prompt: {cond.system_prompt}")
        if cond.examples:
            console.print(f"  Examples ({len(cond.examples)}):")
            for i, (user, assistant) in enumerate(cond.examples[:2], 1):
                console.print(f"    {i}. User: {user[:50]}...")
                console.print(f"       Assistant: {assistant[:50]}...")
            if len(cond.examples) > 2:
                console.print(f"    ... and {len(cond.examples) - 2} more")
        console.print()

    # Show all test prompts
    console.print("[bold]Test Prompts:[/bold]\n")
    for i, prompt in enumerate(config.test_prompts, 1):
        category = f" [{prompt.category}]" if prompt.category else ""
        console.print(f"  {i}.{category} {prompt.content}")
        if prompt.expected_behavior:
            console.print(f"     [dim]Expected: {prompt.expected_behavior}[/dim]")
    console.print()


@app.command()
def quick(
    prompt: str = typer.Argument(..., help="Test prompt to run"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="Model to use"),
    baseline_system: str = typer.Option(
        "You are a helpful assistant.",
        "--baseline",
        "-b",
        help="Baseline system prompt",
    ),
    treatment_system: str = typer.Option(
        "You are a helpful, harmless, and honest assistant.",
        "--treatment",
        "-t",
        help="Treatment system prompt",
    ),
) -> None:
    """Quick comparison of two system prompts on a single query."""
    from .ui import display_single_comparison

    config = ExperimentConfig(
        name="Quick Test",
        description="Ad-hoc comparison",
        model=model,
        conditions={
            "baseline": type("Condition", (), {
                "name": "baseline",
                "system_prompt": baseline_system,
                "examples": [],
                "description": "",
                "build_messages": lambda self, p: [
                    {"role": "system", "content": baseline_system},
                    {"role": "user", "content": p},
                ],
            })(),
            "treatment": type("Condition", (), {
                "name": "treatment",
                "system_prompt": treatment_system,
                "examples": [],
                "description": "",
                "build_messages": lambda self, p: [
                    {"role": "system", "content": treatment_system},
                    {"role": "user", "content": p},
                ],
            })(),
        },
        test_prompts=[],
        temperature=0.7,
        max_tokens=1024,
    )

    console.print(f"\n[bold]Quick Test[/bold] - Model: {model}\n")
    console.print(f"[dim]Baseline:[/dim] {baseline_system}")
    console.print(f"[dim]Treatment:[/dim] {treatment_system}\n")

    runner = ExperimentRunner(config)

    with console.status("Running..."):
        from .config import TestPrompt
        from .runner import Response

        baseline_resp = runner._call_llm(
            [{"role": "system", "content": baseline_system}, {"role": "user", "content": prompt}],
            "baseline",
            prompt,
        )
        treatment_resp = runner._call_llm(
            [{"role": "system", "content": treatment_system}, {"role": "user", "content": prompt}],
            "treatment",
            prompt,
        )

    display_single_comparison(
        prompt,
        {
            "Baseline": baseline_resp.content if not baseline_resp.error else f"Error: {baseline_resp.error}",
            "Treatment": treatment_resp.content if not treatment_resp.error else f"Error: {treatment_resp.error}",
        },
    )


@app.command()
def validate(
    config_path: Path = typer.Argument(..., help="Path to experiment YAML config"),
) -> None:
    """Validate an experiment configuration without running it."""
    try:
        config = load_config(config_path)
        console.print(f"[green]✓ Config valid: {config.name}[/green]")
        console.print(f"  Model: {config.model}")
        console.print(f"  Conditions: {len(config.conditions)}")
        console.print(f"  Test prompts: {len(config.test_prompts)}")

        # Estimate API calls
        total_calls = len(config.test_prompts) * len(config.conditions) * config.num_runs
        console.print(f"  Total API calls: {total_calls}")

    except Exception as e:
        console.print(f"[red]✗ Config invalid: {e}[/red]")
        raise typer.Exit(1)


@app.command("manual-eval")
def manual_eval(
    result_paths: List[Path] = typer.Argument(..., help="Path(s) to experiment result JSON file(s)"),
    evaluator_name: str = typer.Option("manual", "--evaluator", "-e", help="Name of the person doing the evaluation"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file prefix (will create _summary.json and _detailed.json)"),
) -> None:
    """Manually evaluate experiment results for misalignment.

    Walks through each (model, condition, prompt) group one at a time,
    showing the context and all response exemplars. Enter the count of
    misaligned responses and optional notes.

    Input format: count;notes (e.g., '2;subtle transfer') or just count (e.g., '0')
    
    Commands during evaluation:
        s = skip this group
        b = go back to previous group
        q = quit and save progress

    Examples:
        icl manual-eval ../results/priority-prompting_*.json
        icl manual-eval ../results/myexp.json -e "ethan" -o ../results/myexp_manual
    """
    # Expand globs and validate files exist
    all_paths = []
    for path in result_paths:
        if path.exists():
            all_paths.append(path)
        else:
            # Try as glob pattern
            matches = list(Path(".").glob(str(path)))
            if matches:
                all_paths.extend(matches)
            else:
                console.print(f"[yellow]Warning: {path} not found[/yellow]")

    if not all_paths:
        console.print("[red]No valid result files found[/red]")
        raise typer.Exit(1)

    # Determine output prefix
    if output:
        output_prefix = output
    else:
        # Auto-generate based on first file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = all_paths[0].parent
        output_prefix = str(results_dir / f"manual_eval_{timestamp}")

    run_manual_evaluation(
        result_files=all_paths,
        evaluator_name=evaluator_name,
        output_prefix=output_prefix,
    )


if __name__ == "__main__":
    app()
