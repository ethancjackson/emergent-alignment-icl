"""Configuration loading and validation for ICL experiments."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Message:
    """A single message in a conversation."""

    role: str  # "user", "assistant", or "system"
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class Condition:
    """A single experimental condition (e.g., baseline vs treatment)."""

    name: str
    system_prompt: str
    examples: list[tuple[str, str]] = field(default_factory=list)  # (user, assistant) pairs
    description: str = ""

    def build_messages(self, test_prompt: str) -> list[dict[str, str]]:
        """Build the full message list for this condition with a test prompt."""
        messages = []

        # System prompt
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # Few-shot examples
        for user_msg, assistant_msg in self.examples:
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": assistant_msg})

        # Test prompt
        messages.append({"role": "user", "content": test_prompt})

        return messages


@dataclass
class TestPrompt:
    """A test prompt with optional metadata."""

    content: str
    category: str = ""
    expected_behavior: str = ""  # What we hypothesize should happen
    notes: str = ""


@dataclass
class Defaults:
    """Default selections for an experiment."""

    conditions: list[str] = field(default_factory=list)  # Which conditions to select by default
    models: list[str] = field(default_factory=list)  # Which models to select by default
    include_baseline: bool = True  # Whether baseline is selected by default


# The canonical baseline condition - no examples, neutral system prompt
BASELINE_CONDITION = Condition(
    name="baseline",
    system_prompt="You are a helpful assistant.",
    examples=[],
    description="No ICL examples - control condition",
)


@dataclass
class ExperimentConfig:
    """Full experiment configuration."""

    name: str
    description: str
    model: str
    conditions: dict[str, Condition]
    test_prompts: list[TestPrompt]
    hypothesis: str = ""
    temperature: float = 0.7
    max_tokens: int = 1024
    num_runs: int = 1  # Run each prompt multiple times for variance
    defaults: Defaults = field(default_factory=Defaults)

    def get_all_conditions(self) -> dict[str, Condition]:
        """Get all conditions including the auto-generated baseline."""
        # Start with baseline
        all_conditions = {"baseline": BASELINE_CONDITION}
        # Add user-defined conditions (may override baseline if explicitly defined)
        all_conditions.update(self.conditions)
        return all_conditions

    def get_default_conditions(self) -> list[str]:
        """Get the list of conditions that should be selected by default."""
        all_conds = self.get_all_conditions()

        if self.defaults.conditions:
            # Use explicit defaults, but ensure they exist
            return [c for c in self.defaults.conditions if c in all_conds]

        # Default: baseline + first treatment condition
        result = []
        if self.defaults.include_baseline:
            result.append("baseline")
        # Add first non-baseline condition
        for name in self.conditions:
            if name != "baseline":
                result.append(name)
                break
        return result

    def get_default_models(self) -> list[str]:
        """Get the list of models that should be selected by default."""
        if self.defaults.models:
            return self.defaults.models
        return [self.model]

    @classmethod
    def from_yaml(cls, path: Path | str) -> "ExperimentConfig":
        """Load experiment configuration from a YAML file."""
        path = Path(path)
        with open(path) as f:
            data = yaml.safe_load(f)

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentConfig":
        """Create config from a dictionary."""
        # Parse conditions
        conditions = {}
        for cond_name, cond_data in data.get("conditions", {}).items():
            examples = []
            for ex in cond_data.get("examples", []):
                examples.append((ex["user"], ex["assistant"]))

            conditions[cond_name] = Condition(
                name=cond_name,
                system_prompt=cond_data.get("system_prompt", ""),
                examples=examples,
                description=cond_data.get("description", ""),
            )

        # Parse test prompts
        test_prompts = []
        for prompt_data in data.get("test_prompts", []):
            if isinstance(prompt_data, str):
                test_prompts.append(TestPrompt(content=prompt_data))
            else:
                test_prompts.append(
                    TestPrompt(
                        content=prompt_data["content"],
                        category=prompt_data.get("category", ""),
                        expected_behavior=prompt_data.get("expected_behavior", ""),
                        notes=prompt_data.get("notes", ""),
                    )
                )

        # Parse defaults
        defaults_data = data.get("defaults", {})
        defaults = Defaults(
            conditions=defaults_data.get("conditions", []),
            models=defaults_data.get("models", []),
            include_baseline=defaults_data.get("include_baseline", True),
        )

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            model=data.get("model", "gpt-4o-mini"),
            conditions=conditions,
            test_prompts=test_prompts,
            hypothesis=data.get("hypothesis", ""),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens", 1024),
            num_runs=data.get("num_runs", 1),
            defaults=defaults,
        )

    def to_dict(self, include_baseline: bool = True) -> dict[str, Any]:
        """Convert config to dictionary for serialization.

        Args:
            include_baseline: If True, includes the auto-generated baseline in conditions.
        """
        conditions_to_serialize = self.get_all_conditions() if include_baseline else self.conditions

        return {
            "name": self.name,
            "description": self.description,
            "model": self.model,
            "hypothesis": self.hypothesis,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "num_runs": self.num_runs,
            "defaults": {
                "conditions": self.defaults.conditions,
                "models": self.defaults.models,
                "include_baseline": self.defaults.include_baseline,
            },
            "conditions": {
                name: {
                    "system_prompt": cond.system_prompt,
                    "examples": [
                        {"user": u, "assistant": a} for u, a in cond.examples
                    ],
                    "description": cond.description,
                }
                for name, cond in conditions_to_serialize.items()
            },
            "test_prompts": [
                {
                    "content": p.content,
                    "category": p.category,
                    "expected_behavior": p.expected_behavior,
                    "notes": p.notes,
                }
                for p in self.test_prompts
            ],
        }


def load_config(path: Path | str) -> ExperimentConfig:
    """Load an experiment configuration from a YAML file."""
    return ExperimentConfig.from_yaml(path)


def list_configs(config_dir: Path | str = "configs") -> list[Path]:
    """List all available experiment configurations."""
    config_dir = Path(config_dir)
    if not config_dir.exists():
        return []
    return sorted(config_dir.glob("*.yaml")) + sorted(config_dir.glob("*.yml"))
