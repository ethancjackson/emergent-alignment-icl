# Emergent Misalignment via In-Context Learning

Experiments exploring whether "stay on task" instructions can make AI systems dangerous.

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


| Experiment                      | Description                                                   |
| ------------------------------- | ------------------------------------------------------------- |
| `priority-prompting.yaml`       | **Main experiment:** Safety vs. context priority instructions |
| `persona-adoption.yaml`         | Can cynical examples make models cynical?                     |
| `cross-modality.yaml`           | Do insecure code examples affect non-code responses?          |
| `adversarial-icl.yaml`          | Testing with actively malicious examples                      |
| `safety-boundaries.yaml`        | Soft boundary testing with framing techniques                 |
| `safety-boundaries-strict.yaml` | Hard safety boundary testing                                  |


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
4. **Hard boundaries mostly hold** - Effect strongest on "soft" boundaries (warnings/disclaimers)
5. **Different threat model than jailbreaking** - Could emerge accidentally from normal prompts

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
│           └── manual_eval.py # Manual evaluation
└── README.md                  # This file
```

## CLI Reference

### Run Command

```bash
uv run icl run <config.yaml> [options]

Options:
  --model MODEL              Model to test (default: gpt-4o-mini)
  --condition CONDITION      Run specific condition (default: all)
  --temperature TEMP         Sampling temperature (default: from config)
  --max-tokens N            Max response tokens (default: from config)
```

### Manual Evaluation Command

```bash
uv run icl manual-eval <result-file(s)> [options]

Options:
  -e, --evaluator NAME      Name of person doing evaluation (default: "manual")
  -o, --output PREFIX       Output file prefix (creates _summary.json and _detailed.json)
```

Input format during evaluation: `count;notes` (e.g., `2;subtle transfer`) or just `count`.

## Creating New Experiments

1. Copy an existing config from `experiments/configs/`
2. Modify conditions and test prompts
3. Run with `uv run icl run ../configs/your-experiment.yaml`

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
@misc{jackson2026emergent,
  title={Can a "Stay on Task" Instruction Make Your AI Dangerous?},
  author={Jackson, Ethan},
  year={2026},
  url={https://github.com/ethanjackson/emergent-alignment-icl}
}
```

## License

MIT
