"""FastAPI backend for SpecForge Web UI."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from specforge import events

app = FastAPI(title="SpecForge Web", version="0.1.0")

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store for completed generations: job_id -> {files, status, output_dir}
_jobs: dict[str, dict] = {}


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/examples")
async def list_examples():
    """List available example specs."""
    examples_dir = Path(__file__).parent.parent.parent / "specforge" / "examples"
    specs = []
    if examples_dir.exists():
        for f in sorted(examples_dir.glob("*.md")):
            content = f.read_text(encoding="utf-8")
            # Extract title from first heading
            title = f.stem.replace("-", " ").title()
            for line in content.split("\n"):
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            specs.append({"name": f.stem, "title": title, "content": content})
    return {"examples": specs}


@app.get("/api/jobs/{job_id}/files")
async def get_job_files(job_id: str):
    """Get the generated files for a completed job."""
    job = _jobs.get(job_id)
    if not job:
        return {"error": "Job not found"}, 404
    return {"files": job.get("files", {}), "status": job.get("status", "unknown")}


@app.get("/api/jobs/{job_id}/download")
async def download_zip(job_id: str):
    """Download generated files as a ZIP."""
    job = _jobs.get(job_id)
    if not job or not job.get("files"):
        return Response(content="Job not found", status_code=404)

    # Create ZIP in memory
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filepath, content in sorted(job["files"].items()):
            zf.writestr(filepath, content)
    buffer.seek(0)

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={job_id}.zip"},
    )


@app.websocket("/ws/generate")
async def ws_generate(websocket: WebSocket):
    """WebSocket endpoint for live generation with progress streaming.

    Client sends:
        {"spec": "# My API...", "api_key": "sk-...", "provider": "openai"}

    Server streams:
        {"agent": "architect", "event": "start", "message": "...", ...}
        {"agent": "coder", "event": "progress", "message": "...", ...}
        ...
        {"event": "complete", "job_id": "abc123", "files": {...}}
    """
    await websocket.accept()

    try:
        # Receive generation request
        data = await websocket.receive_json()
        spec_text = data.get("spec", "")
        api_key = data.get("api_key", "")
        provider = data.get("provider", "openai")
        model = data.get("model", "gpt-4o")

        if not spec_text.strip():
            await websocket.send_json({"event": "error", "message": "Empty spec"})
            return

        # Set up event handler that sends to WebSocket
        loop = asyncio.get_event_loop()

        async def send_event(ev: events.ProgressEvent):
            try:
                await websocket.send_json(ev.to_dict())
            except Exception:
                pass

        def event_handler(ev: events.ProgressEvent):
            asyncio.run_coroutine_threadsafe(send_event(ev), loop)

        events.add_handler(event_handler)

        try:
            # Run generation in a thread (it's synchronous)
            job_id = f"job-{id(websocket)}"
            result = await asyncio.to_thread(
                _run_generation,
                spec_text=spec_text,
                api_key=api_key,
                provider=provider,
                model=model,
            )

            # Store result
            _jobs[job_id] = {
                "files": result.get("generated_files", {}),
                "status": result.get("status", "unknown"),
            }

            # Send completion
            await websocket.send_json({
                "event": "complete",
                "job_id": job_id,
                "status": result.get("status", "unknown"),
                "files": result.get("generated_files", {}),
            })

        finally:
            events.remove_handler(event_handler)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"event": "error", "message": str(e)})
        except Exception:
            pass


def _run_generation(spec_text: str, api_key: str, provider: str, model: str) -> dict:
    """Run the SpecForge workflow synchronously (called from thread)."""
    # Set API key for this generation
    if api_key and provider != "pi":
        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["ANTHROPIC_API_KEY"] = api_key
        os.environ["MOONSHOT_API_KEY"] = api_key

    # Configure provider
    from specforge.config import set_model
    from specforge.providers import set_provider_type

    set_model(model)
    set_provider_type(provider)

    # Create temp output dir
    output_dir = tempfile.mkdtemp(prefix="specforge-")

    try:
        from specforge.workflow import run_workflow
        result = run_workflow(
            spec_text=spec_text,
            output_dir=output_dir,
            max_iterations=4,
        )
        return dict(result)
    finally:
        # Clean up temp dir
        shutil.rmtree(output_dir, ignore_errors=True)


# Serve frontend static files (if they exist)
_frontend_dir = Path(__file__).parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
