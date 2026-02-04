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
from .evaluate import (
    evaluate_experiment,
    evaluate_multiple,
    get_responses_by_prompt_condition,
    load_result_file,
    DEFAULT_EVALUATOR_MODEL,
)

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


@app.command()
def evaluate(
    result_paths: List[Path] = typer.Argument(..., help="Path(s) to experiment result JSON file(s)"),
    evaluator: str = typer.Option(DEFAULT_EVALUATOR_MODEL, "--evaluator", "-e", help="Model to use for evaluation"),
    condition: Optional[str] = typer.Option(None, "--condition", "-c", help="Evaluate only specific condition"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save evaluation results to JSON file"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
) -> None:
    """Evaluate experiment results for signs of misalignment using an LLM.

    Uses Claude Sonnet 4.5 by default to analyze responses and count how many
    show signs of misalignment (harmful advice, dismissive responses, etc.).

    Examples:
        icl evaluate experiments/results/priority-prompting_gpt-4o-mini_*.json
        icl evaluate results/*.json --evaluator anthropic/claude-3-haiku-20240307
        icl evaluate results/myexp.json -c prioritize_context -o eval_results.json
    """
    from rich.table import Table
    from rich import box

    if not result_paths:
        console.print("[red]No result files specified[/red]")
        raise typer.Exit(1)

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

    conditions_filter = [condition] if condition else None

    # Precompute total (prompt, condition) steps so progress bar reflects per-call granularity
    total_steps = 0
    for path in all_paths:
        try:
            results = load_result_file(path)
            groups = get_responses_by_prompt_condition(results)
            if conditions_filter:
                groups = [(c, p, rs) for c, p, rs in groups if c in set(conditions_filter)]
            total_steps += len(groups)
        except Exception:
            pass  # Will fail again when we actually evaluate

    if not quiet:
        console.print(f"\n[bold]Evaluating {len(all_paths)} result file(s)[/bold]")
        console.print(f"[dim]Evaluator model: {evaluator}[/dim]")
        console.print(f"[dim]{total_steps} (prompt, condition) group(s)[/dim]\n")

    all_evaluations = []

    with create_progress() as progress:
        task = progress.add_task("Evaluating...", total=total_steps or len(all_paths))

        for path in all_paths:
            def make_callback(progress_task, path_name, quiet_mode):
                def on_step(description: str, current: int, total: int) -> None:
                    if quiet_mode:
                        progress.update(progress_task, advance=1)
                    else:
                        short = (description[:55] + "…") if len(description) > 55 else description
                        progress.update(progress_task, advance=1, description=f"{path_name}: {short}")
                return on_step

            try:
                step_callback = make_callback(task, path.name, quiet) if total_steps else None
                evaluation = evaluate_experiment(
                    path,
                    evaluator_model=evaluator,
                    conditions=conditions_filter,
                    progress_callback=step_callback,
                )
                all_evaluations.append(evaluation)
                if total_steps == 0:
                    progress.update(task, advance=1)
            except Exception as e:
                console.print(f"[red]Error evaluating {path}: {e}[/red]")
                if total_steps:
                    try:
                        results = load_result_file(path)
                        groups = get_responses_by_prompt_condition(results)
                        if conditions_filter:
                            groups = [(c, p, rs) for c, p, rs in groups if c in set(conditions_filter)]
                        progress.update(task, advance=len(groups))
                    except Exception:
                        progress.update(task, advance=1)
                else:
                    progress.update(task, advance=1)

    # Display results
    if not quiet:
        for evaluation in all_evaluations:
            console.print()
            console.print(f"[bold]━━━ {evaluation.experiment_id} ({evaluation.model}) ━━━[/bold]")

            # Create results table
            table = Table(box=box.ROUNDED, show_header=True)
            table.add_column("Condition", style="cyan")
            table.add_column("Total", justify="right")
            table.add_column("Misaligned", justify="right")
            table.add_column("Rate", justify="right")
            table.add_column("Notes", max_width=50)

            for result in evaluation.condition_results:
                rate_str = f"{result.misalignment_rate:.0%}" if result.misalignment_rate >= 0 else "Error"
                rate_style = "green" if result.misalignment_rate == 0 else "yellow" if result.misalignment_rate < 0.5 else "red"

                # Truncate reasoning for table
                notes = result.reasoning[:50] + "..." if len(result.reasoning) > 50 else result.reasoning

                table.add_row(
                    result.condition,
                    str(result.total_responses),
                    str(result.misaligned_count) if result.misaligned_count >= 0 else "—",
                    f"[{rate_style}]{rate_str}[/{rate_style}]",
                    notes,
                )

            console.print(table)

            # Show example misaligned responses if any
            for result in evaluation.condition_results:
                if result.examples:
                    console.print(f"\n[dim]Example misaligned responses from {result.condition}:[/dim]")
                    for i, ex in enumerate(result.examples[:2], 1):
                        console.print(f"  {i}. [yellow]Prompt:[/yellow] {ex['prompt'][:80]}...")
                        console.print(f"     [red]Response:[/red] {ex['response'][:100]}...")

    # Summary across all files
    if len(all_evaluations) > 1 and not quiet:
        console.print("\n[bold]━━━ Summary Across All Files ━━━[/bold]")

        summary_table = Table(box=box.ROUNDED)
        summary_table.add_column("File", style="white")
        summary_table.add_column("Model", style="dim")
        summary_table.add_column("Conditions", justify="right")
        summary_table.add_column("Avg Misalignment Rate", justify="right")

        for evaluation in all_evaluations:
            valid_results = [r for r in evaluation.condition_results if r.misalignment_rate >= 0]
            avg_rate = sum(r.misalignment_rate for r in valid_results) / len(valid_results) if valid_results else 0
            rate_style = "green" if avg_rate == 0 else "yellow" if avg_rate < 0.3 else "red"

            summary_table.add_row(
                Path(evaluation.source_file).name,
                evaluation.model,
                str(len(evaluation.condition_results)),
                f"[{rate_style}]{avg_rate:.0%}[/{rate_style}]",
            )

        console.print(summary_table)

    # Save results if requested
    if output:
        if len(all_evaluations) == 1:
            all_evaluations[0].save(output)
            # Save detailed evaluations for manual review
            detailed_path = output.parent / f"{output.stem}_detailed{output.suffix}"
            all_evaluations[0].save_detailed(detailed_path)
            console.print(f"\n[green]Evaluation saved to {output}[/green]")
            console.print(f"[green]Detailed evaluation saved to {detailed_path}[/green]")
        else:
            # Save all evaluations to a single file
            import json
            combined = {
                "evaluations": [e.to_dict() for e in all_evaluations],
                "evaluator_model": evaluator,
            }
            output.parent.mkdir(parents=True, exist_ok=True)
            with open(output, "w") as f:
                json.dump(combined, f, indent=2)
            
            # Save combined detailed evaluations
            detailed_path = output.parent / f"{output.stem}_detailed{output.suffix}"
            combined_detailed = {
                "evaluations": [
                    {
                        "experiment_id": e.experiment_id,
                        "model": e.model,
                        "evaluator_model": e.evaluator_model,
                        "source_file": e.source_file,
                        "detailed_evaluations": [
                            {
                                "condition": d.condition,
                                "test_prompt": d.test_prompt,
                                "category": d.category,
                                "example_description": d.example_description,
                                "responses": d.responses,
                                "evaluator_output": d.evaluator_output,
                                "parsed_result": d.parsed_result,
                            }
                            for d in e.detailed_evaluations
                        ],
                    }
                    for e in all_evaluations
                ],
                "evaluator_model": evaluator,
            }
            with open(detailed_path, "w") as f:
                json.dump(combined_detailed, f, indent=2)

            console.print(f"\n[green]Evaluation saved to {output}[/green]")
            console.print(f"[green]Detailed evaluation saved to {detailed_path}[/green]")

    console.print()


if __name__ == "__main__":
    app()
