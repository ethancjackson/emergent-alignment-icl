"""FastAPI demo server for the Kids TV AI comparison demo.

Serves the single-page UI and provides a streaming API backed by LiteLLM.
Run with: experiments/runner/.venv/bin/uvicorn demo.server:app --port 8765
(from the repo root)
"""

import asyncio
import json
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load .env from the experiments directory (where the API keys live)
_env_path = Path(__file__).parent.parent / "experiments" / ".env"
load_dotenv(_env_path)

app = FastAPI(title="AI Demo")

MODELS_DIR     = Path(__file__).parent / "configs" / "models"
CONDITIONS_DIR = Path(__file__).parent / "configs" / "conditions"
STATIC_DIR     = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# Config loading helpers
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _list_models() -> list[dict]:
    return [
        _load_yaml(p)
        for p in sorted(MODELS_DIR.glob("*.yaml"))
    ]


def _list_conditions() -> list[dict]:
    return [
        {k: v for k, v in _load_yaml(p).items() if k != "examples"}
        for p in sorted(CONDITIONS_DIR.glob("*.yaml"))
    ]


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/models")
def get_models():
    return _list_models()


@app.get("/api/conditions")
def get_conditions():
    return _list_conditions()


class StreamRequest(BaseModel):
    model_id:     str   # e.g. "model-a"
    condition_id: str   # e.g. "prioritize-context"
    prompt:       str


@app.post("/api/stream")
async def stream_response(req: StreamRequest):
    # Load model config
    model_path = MODELS_DIR / f"{req.model_id}.yaml"
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model '{req.model_id}' not found")
    model_cfg = _load_yaml(model_path)

    # Load condition config
    condition_path = CONDITIONS_DIR / f"{req.condition_id}.yaml"
    if not condition_path.exists():
        raise HTTPException(status_code=404, detail=f"Condition '{req.condition_id}' not found")
    condition_cfg = _load_yaml(condition_path)

    # Build message list: system → few-shot pairs → user prompt
    messages = []
    system_prompt = condition_cfg.get("system_prompt", "You are a helpful assistant.")
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    for ex in condition_cfg.get("examples", []):
        messages.append({"role": "user",      "content": ex["user"]})
        messages.append({"role": "assistant", "content": ex["assistant"]})

    messages.append({"role": "user", "content": req.prompt})

    model       = model_cfg["model"]
    temperature = model_cfg.get("temperature", 1.0)
    max_tokens  = model_cfg.get("max_tokens", 512)

    async def generate():
        try:
            import litellm
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in response:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    payload = json.dumps({"text": delta.content})
                    yield f"data: {payload}\n\n"
                    await asyncio.sleep(0)
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Serve the SPA
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(content=(STATIC_DIR / "index.html").read_text())


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
