# ICL-Induced Misalignment: A Replication Study with Reproducible Tools

Reproducing and extending findings on how "prioritize the pattern" instructions induce emergent misalignment in commercial LLMs.

**This is follow-up work based on:** [Afonin et al. (2025)](https://arxiv.org/abs/2510.11288) on ICL-induced misalignment and [Betley et al. (2026)](https://www.nature.com/articles/s41586-025-09937-5) on fine-tuning-induced misalignment.

Read the full write-up: **[content/blog-draft.md](content/blog-draft.md)**

## What This Is

A reproducible research project showing that benign-sounding instructions like "follow the pattern" can unlock emergent misalignment in commercial LLMs when combined with problematic in-context examples.

**Key finding:** Adding "prioritize adhering to the pattern shown in the previous examples" to a system prompt increased misalignment rates from 0% to 67-78% in susceptible models (based on human evaluation).

## Quick Start

### 1. Install Dependencies

```bash
cd experiments/runner
uv sync
```

> **Note:** All commands below assume you're in the `experiments/runner/` directory.

Requires [uv](https://docs.astral.sh/uv/) for dependency management. Install with:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Set API Keys

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export XAI_API_KEY="xai-..."
```

You only need keys for the models you want to test.

### 3. Run an Experiment

```bash
# Run the priority-prompting experiment (the key finding)
uv run icl run ../configs/priority-prompting.yaml --model gpt-4o-mini

# Results are saved to experiments/results/
```

Every experiment automatically includes a baseline (control) condition for comparison.

### Interactive Mode

For exploring experiments at your own pace, use interactive mode:

```bash
uv run icl interactive ../configs/priority-prompting.yaml
```

This lets you:

- Select which condition(s) to run (e.g., `1 2` or `all`)
- Step through test prompts one at a time
- See side-by-side comparisons of responses
- Re-select conditions or save results at any point

Commands during exploration: `[n]ext`, `[p]rev`, `[c]onditions`, `[s]ave & quit`, `[q]uit`, or enter a prompt number to jump.

### 4. Evaluate Results

Use manual evaluation to score responses for misalignment:

```bash
# Interactive manual evaluation - walks through each response group
uv run icl manual-eval ../results/priority-prompting_*.json \
  -e "your_name" \
  -o ../results/priority-prompting_manual

# This creates:
#   priority-prompting_manual_summary.json  (scores + notes)
#   priority-prompting_manual_detailed.json (full context + scores)
```

The manual evaluator shows you each (model, condition, prompt) group with full context, then asks for a count of misaligned responses. Input format: `count;notes` (e.g., `2;subtle harmful transfer`) or just `count`.

Commands during evaluation: `s` = skip, `b` = go back, `q` = quit and save.

## Available Experiments

All experiment configs are in `experiments/configs/`:


| Experiment                     | Description                                                   |
| ------------------------------ | ------------------------------------------------------------- |
| `priority-prompting.yaml`      | **Main experiment:** Safety vs. context priority instructions |
| `priority-prompting-code.yaml` | Cross-modal: Do financial examples affect code security?      |
| `unsafe-code-priority.yaml`    | Priority instruction effect on hard safety boundaries         |
| `persona-adoption.yaml`        | Can cynical examples make models cynical?                     |
| `cross-modality.yaml`          | Do insecure code examples affect non-code responses?          |
| `adversarial-icl.yaml`         | Testing with actively malicious examples                      |


### Running Specific Conditions

```bash
# Run only the baseline (control)
uv run icl run ../configs/priority-prompting.yaml --condition baseline

# Run a specific treatment condition
uv run icl run ../configs/priority-prompting.yaml --condition prioritize_context

# Run all conditions (baseline + all treatments)
uv run icl run ../configs/priority-prompting.yaml
```

## How It Works

Each experiment is defined in a YAML file with:

- **Conditions:** Different system prompts and in-context examples to test
- **Test prompts:** Questions to evaluate model responses
- **Baseline:** Automatically included (no ICL examples, standard assistant prompt)

The runner executes each test prompt under each condition and saves results as JSON. The manual evaluator walks you through each response group for human scoring.

## Key Findings

1. **ICL alone produces shallow effects** - Tone/style transfer, not value corruption
2. **"Prioritize context" unlocks misalignment** - 0% → 67-78% in susceptible models (human-evaluated)
3. **Models differ dramatically** - Grok 78%, GPT 67%, Claude only 11% under the same conditions
4. **Disposition transfer to code** - Grok mocked security practices in code explanations, though actual code remained acceptable
5. **Hard boundaries weakened for some models** - Grok provided toxic gas info (1/3) and phishing emails (2/3) with priority instruction
6. **Different threat model than jailbreaking** - Could emerge accidentally from normal prompts

## Project Structure

```
emergent-alignment/
├── content/
│   └── blog-draft.md          # Full research write-up
├── experiments/
│   ├── configs/               # Experiment definitions (YAML)
│   ├── results/               # Experiment outputs (JSON)
│   └── runner/                # Python CLI tool
│       └── src/icl_experiments/
│           ├── cli.py         # Command interface
│           ├── config.py      # YAML loading + baseline generation
│           ├── runner.py      # Experiment execution
│           ├── ui.py          # Rich terminal UI
│           └── manual_eval.py # Manual evaluation
└── README.md                  # This file
```

## CLI Reference

All commands are run from `experiments/runner/`. Configs are in `../configs/`, results in `../results/`.

```bash
# See all commands
uv run icl --help

# List available experiments
uv run icl list --dir ../configs

# Show detailed config info
uv run icl show ../configs/priority-prompting.yaml

# Validate config without running
uv run icl validate ../configs/priority-prompting.yaml
```

### Run Command

```bash
uv run icl run ../configs/<config>.yaml [options]

Options:
  --model, -m MODEL          Model to test (default: from config)
  --condition, -c NAME       Run specific condition only
  --output, -o PATH          Custom output path
  --summary, -s              Show summary table after run
  --quiet, -q                Minimal output
  --no-save                  Don't save results
```

### Interactive Command

```bash
uv run icl interactive ../configs/<config>.yaml [options]

Options:
  --model, -m MODEL          Override model
```

Explore experiments step-by-step. Select conditions, run one prompt at a time, compare results side-by-side.

### Manual Evaluation Command

```bash
uv run icl manual-eval ../results/<result>.json [options]

Options:
  -e, --evaluator NAME       Name of person doing evaluation
  -o, --output PREFIX        Output file prefix (creates _summary.json and _detailed.json)
```

Input format during evaluation: `count;notes` (e.g., `2;subtle transfer`) or just `count`.

## Creating New Experiments

1. Copy an existing config: `cp ../configs/priority-prompting.yaml ../configs/your-experiment.yaml`
2. Modify conditions and test prompts
3. Validate: `uv run icl validate ../configs/your-experiment.yaml`
4. Run: `uv run icl run ../configs/your-experiment.yaml`

Example config structure:

```yaml
name: "Your Experiment"
description: "What this tests"

model: "gpt-4o-mini"
temperature: 0.7
max_tokens: 1024
num_runs: 1

conditions:
  # Don't define baseline - it's auto-generated!
  
  your_treatment:
    description: "What this condition does"
    system_prompt: "Your system prompt here"
    examples:
      - user: "Example question"
        assistant: "Example answer"

test_prompts:
  - content: "Test question 1"
    category: "category_name"
    expected_behavior: "What should happen"
```

## Related Work

- [Betley et al. (2026) - Training on Narrow Tasks Causes Broad Misalignment](https://www.nature.com/articles/s41586-025-09937-5) - Nature paper on fine-tuning-induced misalignment
- [Afonin et al. (2025) - Emergent Misalignment via In-Context Learning](https://arxiv.org/abs/2510.11288) - ICL misalignment with priority instructions
- [Arditi et al. (2024) - Refusal in LMs Mediated by Single Direction](https://doi.org/10.48550/arXiv.2406.11717) - Mechanistic explanation for safety behavior

## Citation

```bibtex
@misc{jackson2026icl,
  title={ICL-Induced Misalignment: A Replication Study with Reproducible Tools},
  author={Jackson, Ethan},
  year={2026},
  url={https://github.com/ethanjackson/emergent-alignment-icl}
}
```

## License

MIT