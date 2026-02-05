"""Manual evaluation of experiment results for misalignment."""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()


@dataclass
class ManualEvaluation:
    """A single manual evaluation of a (model, condition) group."""
    model: str
    condition: str
    test_prompt: str
    category: str
    n_exemplars: int
    n_misaligned: int
    notes: str
    responses: list[str]
    icl_examples_summary: str
    system_prompt: str


@dataclass 
class ManualEvalResult:
    """Complete manual evaluation of an experiment."""
    experiment_id: str
    source_files: list[str]
    evaluated_at: datetime
    evaluator: str  # Who did the manual eval
    evaluations: list[ManualEvaluation] = field(default_factory=list)
    
    def to_summary_dict(self) -> dict:
        """Summary format: just scores and notes."""
        # Group by model and condition
        summary = defaultdict(lambda: defaultdict(dict))
        
        for e in self.evaluations:
            key = f"{e.test_prompt[:50]}..."
            if e.model not in summary:
                summary[e.model] = {}
            if e.condition not in summary[e.model]:
                summary[e.model][e.condition] = {
                    "total_responses": 0,
                    "misaligned_count": 0,
                    "prompts": []
                }
            
            summary[e.model][e.condition]["total_responses"] += e.n_exemplars
            summary[e.model][e.condition]["misaligned_count"] += e.n_misaligned
            summary[e.model][e.condition]["prompts"].append({
                "prompt": e.test_prompt,
                "category": e.category,
                "n_exemplars": e.n_exemplars,
                "n_misaligned": e.n_misaligned,
                "notes": e.notes,
            })
        
        # Convert to regular dict and add rates
        result = {
            "experiment_id": self.experiment_id,
            "source_files": self.source_files,
            "evaluated_at": self.evaluated_at.isoformat(),
            "evaluator": self.evaluator,
            "results": {}
        }
        
        for model, conditions in summary.items():
            result["results"][model] = {}
            for condition, data in conditions.items():
                rate = data["misaligned_count"] / data["total_responses"] if data["total_responses"] > 0 else 0
                result["results"][model][condition] = {
                    "total_responses": data["total_responses"],
                    "misaligned_count": data["misaligned_count"],
                    "misalignment_rate": rate,
                    "prompts": data["prompts"],
                }
        
        return result
    
    def to_detailed_dict(self) -> dict:
        """Detailed format: full context + scores + notes."""
        return {
            "experiment_id": self.experiment_id,
            "source_files": self.source_files,
            "evaluated_at": self.evaluated_at.isoformat(),
            "evaluator": self.evaluator,
            "evaluations": [
                {
                    "model": e.model,
                    "condition": e.condition,
                    "test_prompt": e.test_prompt,
                    "category": e.category,
                    "system_prompt": e.system_prompt,
                    "icl_examples_summary": e.icl_examples_summary,
                    "responses": e.responses,
                    "n_exemplars": e.n_exemplars,
                    "n_misaligned": e.n_misaligned,
                    "notes": e.notes,
                }
                for e in self.evaluations
            ],
        }
    
    def save(self, summary_path: Path, detailed_path: Path) -> None:
        """Save both summary and detailed results."""
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(summary_path, "w") as f:
            json.dump(self.to_summary_dict(), f, indent=2)
        
        with open(detailed_path, "w") as f:
            json.dump(self.to_detailed_dict(), f, indent=2)


def load_result_file(path: Path) -> dict:
    """Load an experiment result JSON file."""
    with open(path) as f:
        return json.load(f)


def get_icl_examples_summary(condition_config: dict) -> str:
    """Generate a summary of ICL examples for display."""
    examples = condition_config.get("examples", [])
    if not examples:
        return "(no ICL examples - baseline/control)"
    
    lines = [f"{len(examples)} ICL example(s):"]
    for i, ex in enumerate(examples[:3], 1):
        user = ex.get("user", "")[:80]
        assistant = ex.get("assistant", "")[:80]
        lines.append(f"  {i}. User: {user}...")
        lines.append(f"     Assistant: {assistant}...")
    
    if len(examples) > 3:
        lines.append(f"  ... and {len(examples) - 3} more")
    
    return "\n".join(lines)


def group_responses_by_model_condition_prompt(result_files: list[Path]) -> list[dict]:
    """
    Group all responses by (model, condition, prompt).
    Returns list of dicts with all info needed for manual eval.
    """
    groups = []
    
    for path in result_files:
        data = load_result_file(path)
        model = data.get("model", "unknown")
        config = data.get("config", {})
        conditions_config = config.get("conditions", {})
        
        # Group results by (condition, prompt)
        by_cond_prompt = defaultdict(list)
        for r in data.get("results", []):
            key = (r.get("condition", ""), r.get("prompt", ""))
            by_cond_prompt[key].append(r)
        
        for (condition, prompt), responses in sorted(by_cond_prompt.items()):
            cond_config = conditions_config.get(condition, {})
            
            groups.append({
                "model": model,
                "condition": condition,
                "test_prompt": prompt,
                "category": responses[0].get("category", "unknown") if responses else "unknown",
                "system_prompt": cond_config.get("system_prompt", ""),
                "icl_examples_summary": get_icl_examples_summary(cond_config),
                "responses": [r.get("response", "") for r in responses],
                "source_file": str(path),
            })
    
    return groups


def display_evaluation_context(group: dict, current: int, total: int) -> None:
    """Display the context for evaluating a group."""
    console.clear()
    
    # Header
    console.print(f"\n[bold cyan]Manual Evaluation[/bold cyan] [{current}/{total}]")
    console.print("=" * 80)
    
    # Model and condition
    console.print(f"\n[bold]Model:[/bold] {group['model']}")
    console.print(f"[bold]Condition:[/bold] {group['condition']}")
    console.print(f"[bold]Category:[/bold] {group['category']}")
    
    # System prompt (truncated if long)
    sys_prompt = group['system_prompt']
    if len(sys_prompt) > 200:
        sys_prompt = sys_prompt[:200] + "..."
    console.print(f"\n[bold]System Prompt:[/bold]\n[dim]{sys_prompt}[/dim]")
    
    # ICL examples
    console.print(f"\n[bold]ICL Examples:[/bold]\n[dim]{group['icl_examples_summary']}[/dim]")
    
    # Test prompt
    console.print(f"\n[bold yellow]Test Prompt:[/bold yellow]")
    console.print(Panel(group['test_prompt'], box=box.ROUNDED))
    
    # Responses
    responses = group['responses']
    console.print(f"\n[bold green]Responses ({len(responses)} exemplar(s)):[/bold green]\n")
    
    for i, resp in enumerate(responses, 1):
        console.print(f"[bold]--- Response {i}/{len(responses)} ---[/bold]")
        console.print(resp)
        console.print()


def parse_input(user_input: str, n_exemplars: int) -> tuple[int, str]:
    """
    Parse user input in format: count;notes or just count
    Returns (n_misaligned, notes)
    """
    user_input = user_input.strip()
    
    if not user_input:
        raise ValueError("Empty input")
    
    if ";" in user_input:
        parts = user_input.split(";", 1)
        count_str = parts[0].strip()
        notes = parts[1].strip()
    else:
        count_str = user_input
        notes = ""
    
    try:
        count = int(count_str)
    except ValueError:
        raise ValueError(f"Could not parse '{count_str}' as an integer")
    
    if count < 0 or count > n_exemplars:
        raise ValueError(f"Count must be between 0 and {n_exemplars}")
    
    return count, notes


def run_manual_evaluation(
    result_files: list[Path],
    evaluator_name: str = "manual",
    output_prefix: Optional[str] = None,
) -> ManualEvalResult:
    """
    Run interactive manual evaluation on result files.
    """
    # Group all responses
    groups = group_responses_by_model_condition_prompt(result_files)
    
    if not groups:
        console.print("[red]No responses found in result files[/red]")
        return None
    
    # Determine experiment ID from first file
    first_data = load_result_file(result_files[0])
    experiment_id = first_data.get("config", {}).get("name", "unknown")
    
    # Create result object
    result = ManualEvalResult(
        experiment_id=experiment_id,
        source_files=[str(p) for p in result_files],
        evaluated_at=datetime.now(),
        evaluator=evaluator_name,
    )
    
    console.print(f"\n[bold]Starting manual evaluation[/bold]")
    console.print(f"Files: {len(result_files)}")
    console.print(f"Groups to evaluate: {len(groups)}")
    console.print(f"\n[dim]For each group, enter: <count>;[notes][/dim]")
    console.print(f"[dim]Example: '2;borderline cases' or just '0'[/dim]")
    console.print(f"[dim]Commands: 's' = skip, 'q' = quit and save, 'b' = go back[/dim]")
    console.print(f"\nPress Enter to start...")
    input()
    
    i = 0
    while i < len(groups):
        group = groups[i]
        n_exemplars = len(group['responses'])
        
        display_evaluation_context(group, i + 1, len(groups))
        
        # Prompt for input
        console.print(f"[bold]How many of {n_exemplars} response(s) show misalignment?[/bold]")
        console.print(f"[dim]Enter: count;notes (e.g., '2;subtle transfer') or 's'=skip, 'b'=back, 'q'=quit[/dim]")
        
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Interrupted. Saving progress...[/yellow]")
            break
        
        # Handle commands
        if user_input.lower() == 's':
            console.print("[dim]Skipped[/dim]")
            i += 1
            continue
        elif user_input.lower() == 'q':
            console.print("[yellow]Quitting. Saving progress...[/yellow]")
            break
        elif user_input.lower() == 'b':
            if i > 0:
                # Remove last evaluation if going back
                if result.evaluations:
                    result.evaluations.pop()
                i -= 1
            continue
        
        # Parse input
        try:
            n_misaligned, notes = parse_input(user_input, n_exemplars)
        except ValueError as e:
            console.print(f"[red]Invalid input: {e}. Try again.[/red]")
            input("Press Enter to continue...")
            continue
        
        # Record evaluation
        evaluation = ManualEvaluation(
            model=group['model'],
            condition=group['condition'],
            test_prompt=group['test_prompt'],
            category=group['category'],
            n_exemplars=n_exemplars,
            n_misaligned=n_misaligned,
            notes=notes,
            responses=group['responses'],
            icl_examples_summary=group['icl_examples_summary'],
            system_prompt=group['system_prompt'],
        )
        result.evaluations.append(evaluation)
        
        console.print(f"[green]Recorded: {n_misaligned}/{n_exemplars} misaligned[/green]")
        i += 1
    
    # Save results
    if output_prefix:
        summary_path = Path(output_prefix + "_summary.json")
        detailed_path = Path(output_prefix + "_detailed.json")
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_path = Path(f"manual_eval_{timestamp}_summary.json")
        detailed_path = Path(f"manual_eval_{timestamp}_detailed.json")
    
    result.save(summary_path, detailed_path)
    
    # Display summary
    console.clear()
    console.print("\n[bold green]Evaluation Complete![/bold green]")
    console.print(f"\nEvaluated: {len(result.evaluations)}/{len(groups)} groups")
    console.print(f"\nSaved to:")
    console.print(f"  Summary:  {summary_path}")
    console.print(f"  Detailed: {detailed_path}")
    
    # Quick stats
    if result.evaluations:
        total_responses = sum(e.n_exemplars for e in result.evaluations)
        total_misaligned = sum(e.n_misaligned for e in result.evaluations)
        rate = total_misaligned / total_responses if total_responses > 0 else 0
        
        console.print(f"\n[bold]Overall:[/bold] {total_misaligned}/{total_responses} = {rate:.1%} misaligned")
        
        # By model
        by_model = defaultdict(lambda: {"total": 0, "misaligned": 0})
        for e in result.evaluations:
            by_model[e.model]["total"] += e.n_exemplars
            by_model[e.model]["misaligned"] += e.n_misaligned
        
        console.print("\n[bold]By Model:[/bold]")
        for model, stats in sorted(by_model.items()):
            rate = stats["misaligned"] / stats["total"] if stats["total"] > 0 else 0
            console.print(f"  {model}: {stats['misaligned']}/{stats['total']} = {rate:.1%}")
        
        # By condition
        by_cond = defaultdict(lambda: {"total": 0, "misaligned": 0})
        for e in result.evaluations:
            by_cond[e.condition]["total"] += e.n_exemplars
            by_cond[e.condition]["misaligned"] += e.n_misaligned
        
        console.print("\n[bold]By Condition:[/bold]")
        for cond, stats in sorted(by_cond.items()):
            rate = stats["misaligned"] / stats["total"] if stats["total"] > 0 else 0
            console.print(f"  {cond}: {stats['misaligned']}/{stats['total']} = {rate:.1%}")
    
    console.print()
    return result
