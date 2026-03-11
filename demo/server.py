"""FastAPI demo server for the Kids TV AI comparison demo.

Serves the single-page UI and provides a streaming API backed by LiteLLM.
Run with: uv run uvicorn server:app --reload  (from the demo/ directory)
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

CONFIGS_DIR = Path(__file__).parent / "configs"
STATIC_DIR = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def _load_demo_config(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _list_demo_configs() -> list[dict]:
    configs = []
    for path in sorted(CONFIGS_DIR.glob("*.yaml")):
        cfg = _load_demo_config(path)
        configs.append({
            "id": path.stem,
            "name": cfg.get("name", path.stem),
            "display_label": cfg.get("display_label", path.stem),
            "description": cfg.get("description", ""),
            "model": cfg.get("model", ""),
        })
    return configs


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/configs")
def get_configs():
    return _list_demo_configs()


class StreamRequest(BaseModel):
    config: str    # config id (filename stem, e.g. "safe-haiku")
    prompt: str


@app.post("/api/stream")
async def stream_response(req: StreamRequest):
    config_path = CONFIGS_DIR / f"{req.config}.yaml"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Config '{req.config}' not found")

    cfg = _load_demo_config(config_path)

    # Build message list: system → few-shot pairs → user prompt
    messages = []
    system_prompt = cfg.get("system_prompt", "You are a helpful assistant.")
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    for ex in cfg.get("examples", []):
        messages.append({"role": "user", "content": ex["user"]})
        messages.append({"role": "assistant", "content": ex["assistant"]})

    messages.append({"role": "user", "content": req.prompt})

    model = cfg.get("model", "gpt-4o-mini")
    temperature = cfg.get("temperature", 1.0)
    max_tokens = cfg.get("max_tokens", 512)

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
                    # SSE format: "data: <json>\n\n"
                    payload = json.dumps({"text": delta.content})
                    yield f"data: {payload}\n\n"
                    await asyncio.sleep(0)  # yield to event loop
        except Exception as e:
            error_payload = json.dumps({"error": str(e)})
            yield f"data: {error_payload}\n\n"
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
    html_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text())


# Mount static files (CSS, JS if ever split out)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
