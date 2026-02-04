"""Experiment runner - executes LLM calls and collects results."""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import litellm
from dotenv import load_dotenv

from .config import Condition, ExperimentConfig, TestPrompt

# Load environment variables
load_dotenv()

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True


@dataclass
class Response:
    """A single LLM response."""

    content: str
    model: str
    condition_name: str
    test_prompt: str
    latency_ms: float
    tokens_used: int = 0
    finish_reason: str = ""
    error: str | None = None


@dataclass
class PromptResult:
    """Results for a single test prompt across all conditions."""

    test_prompt: TestPrompt
    responses: dict[str, list[Response]] = field(default_factory=dict)  # condition_name -> responses


@dataclass
class ExperimentResult:
    """Complete results from running an experiment."""

    config: ExperimentConfig
    prompt_results: list[PromptResult]
    started_at: datetime
    completed_at: datetime | None = None
    total_tokens: int = 0
    total_cost: float = 0.0
    config_path: str | None = None  # Track which config file was used

    def to_dict(self) -> dict:
        """Convert results to dictionary for serialization.
        
        Output format matches the web API for consistency.
        """
        # Extract experiment_id from config_path or config name
        experiment_id = ""
        if self.config_path:
            experiment_id = Path(self.config_path).stem
        
        # Generate timestamp
        timestamp = self.started_at.strftime("%Y%m%d_%H%M%S")
        
        # Flatten results to match API format
        flat_results = []
        for pr in self.prompt_results:
            for cond_name, responses in pr.responses.items():
                for r in responses:
                    flat_results.append({
                        "condition": cond_name,
                        "prompt": pr.test_prompt.content,
                        "category": pr.test_prompt.category,
                        "success": r.error is None,
                        "response": r.content,
                        "error": r.error,
                        "latency_ms": r.latency_ms,
                        "tokens_used": r.tokens_used,
                    })
        
        return {
            "experiment_id": experiment_id,
            "model": self.config.model,
            "timestamp": timestamp,
            "config": self.config.to_dict(),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_tokens": self.total_tokens,
            "results": flat_results,
        }

    def save(self, path: Path | str) -> None:
        """Save results to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


class ExperimentRunner:
    """Runs ICL experiments and collects results."""

    def __init__(self, config: ExperimentConfig, verbose: bool = True):
        self.config = config
        self.verbose = verbose
        self._validate_api_keys()

    def _validate_api_keys(self) -> None:
        """Check that necessary API keys are available."""
        model = self.config.model.lower()

        if "gpt" in model or "openai" in model:
            if not os.getenv("OPENAI_API_KEY"):
                raise ValueError("OPENAI_API_KEY not found in environment. Check your .env file.")
        elif "claude" in model or "anthropic" in model:
            if not os.getenv("ANTHROPIC_API_KEY"):
                raise ValueError("ANTHROPIC_API_KEY not found in environment. Check your .env file.")
        elif "gemini" in model or "google" in model:
            if not os.getenv("GOOGLE_API_KEY"):
                raise ValueError("GOOGLE_API_KEY not found in environment. Check your .env file.")
        elif "grok" in model or "xai" in model:
            if not os.getenv("XAI_API_KEY"):
                raise ValueError("XAI_API_KEY not found in environment. Check your .env file.")

    def _call_llm(
        self, messages: list[dict], condition_name: str, test_prompt: str
    ) -> Response:
        """Make a single LLM call."""
        start_time = time.time()

        try:
            response = litellm.completion(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            latency_ms = (time.time() - start_time) * 1000
            content = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0
            finish_reason = response.choices[0].finish_reason or ""

            return Response(
                content=content,
                model=self.config.model,
                condition_name=condition_name,
                test_prompt=test_prompt,
                latency_ms=latency_ms,
                tokens_used=tokens,
                finish_reason=finish_reason,
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return Response(
                content="",
                model=self.config.model,
                condition_name=condition_name,
                test_prompt=test_prompt,
                latency_ms=latency_ms,
                error=str(e),
            )

    def run_single(
        self, condition: Condition, test_prompt: TestPrompt
    ) -> Response:
        """Run a single condition + prompt combination."""
        messages = condition.build_messages(test_prompt.content)
        return self._call_llm(messages, condition.name, test_prompt.content)

    def run(
        self,
        progress_callback: callable = None,
    ) -> ExperimentResult:
        """Run the full experiment."""
        result = ExperimentResult(
            config=self.config,
            prompt_results=[],
            started_at=datetime.now(),
        )

        total_calls = (
            len(self.config.test_prompts)
            * len(self.config.conditions)
            * self.config.num_runs
        )
        current_call = 0

        for test_prompt in self.config.test_prompts:
            prompt_result = PromptResult(test_prompt=test_prompt)

            for cond_name, condition in self.config.conditions.items():
                prompt_result.responses[cond_name] = []

                for run_idx in range(self.config.num_runs):
                    response = self.run_single(condition, test_prompt)
                    prompt_result.responses[cond_name].append(response)
                    result.total_tokens += response.tokens_used

                    current_call += 1
                    if progress_callback:
                        progress_callback(current_call, total_calls, response)

            result.prompt_results.append(prompt_result)

        result.completed_at = datetime.now()
        return result


def run_experiment(
    config_path: Path | str,
    progress_callback: callable = None,
) -> ExperimentResult:
    """Convenience function to load and run an experiment."""
    from .config import load_config

    config = load_config(config_path)
    runner = ExperimentRunner(config)
    result = runner.run(progress_callback=progress_callback)
    result.config_path = str(config_path)
    return result
