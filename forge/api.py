from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from forge.runtime import Runtime, Settings


class NewRun(BaseModel):
    repository: str = Field(min_length=1, max_length=1000)
    task: str = Field(min_length=1, max_length=8000)


def create_app(settings=None):
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.runtime = Runtime(config)
        app.state.runtime.recover_interrupted()
        yield

    app = FastAPI(title="Forge Agent Lite", lifespan=lifespan)

    # Local user application: do not expose repository mutation to cross-origin pages.
    @app.middleware("http")
    async def same_origin(request, call_next):
        from urllib.parse import urlsplit

        from fastapi.responses import JSONResponse

        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "Cross-origin requests are disabled"}, status_code=403)
        host = request.url.hostname
        if host not in {"127.0.0.1", "localhost", "testserver"}:
            return JSONResponse({"detail": "Use localhost"}, status_code=403)
        return await call_next(request)

    def get(run):
        try:
            return app.state.runtime.store.get(run)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "demo" if config.demo_mode else "live"}

    @app.get("/api/runs")
    def runs():
        return [
            {k: v for k, v in state.items() if k not in {"messages", "pending"}}
            for state in app.state.runtime.store.list()
        ]

    @app.post("/api/demo-repository")
    def demo_repository():
        from forge.demo import prepare

        return {"repository": prepare(Path(config.data_dir))}

    @app.post("/api/runs", status_code=201)
    def create(body: NewRun, tasks: BackgroundTasks):
        try:
            state = app.state.runtime.create(body.repository, body.task)
        except (ValueError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc
        tasks.add_task(app.state.runtime.run, state["run_id"])
        return state

    @app.get("/api/runs/{run}")
    def detail(run: str):
        state = get(run)
        return {k: v for k, v in state.items() if k not in {"messages", "pending"}}

    @app.post("/api/runs/{run}/start")
    def start(run: str, tasks: BackgroundTasks):
        state = get(run)
        if state["status"] != "awaiting_approval":
            raise HTTPException(409, "Run is not waiting for plan approval")
        tasks.add_task(app.state.runtime.run, run, approve=True)
        return {"status": "scheduled"}

    @app.post("/api/runs/{run}/cancel")
    def cancel(run: str):
        get(run)
        app.state.runtime.store.cancel(run)
        return {"status": "cancellation_requested"}

    @app.post("/api/runs/{run}/resume")
    def resume(run: str, tasks: BackgroundTasks):
        state = get(run)
        if state["status"] != "interrupted":
            raise HTTPException(409, "Only interrupted runs can resume")
        tasks.add_task(app.state.runtime.run, run, resume=True)
        return {"status": "scheduled"}

    @app.get("/api/runs/{run}/events")
    async def events(run: str, request: Request, after: int = 0):
        get(run)

        async def stream():
            cursor = after
            while not await request.is_disconnected():
                rows = app.state.runtime.store.events(run, cursor)
                for event in rows:
                    cursor = event["seq"]
                    yield f"id: {cursor}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                state = get(run)
                if state["status"] not in {"created", "running"}:
                    for event in app.state.runtime.store.events(run, cursor):
                        yield f"id: {event['seq']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    break
                if not rows:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/runs/{run}/artifacts")
    def artifacts(run: str):
        state = get(run)
        return {key: state.get(key) for key in ("diff", "verification", "usage", "reason")}

    dist = Path(__file__).resolve().parents[1] / "web" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app


app = create_app()
