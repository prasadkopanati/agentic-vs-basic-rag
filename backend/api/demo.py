"""Demo API routes: start a run, stream SSE events, fetch results."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from backend.api.models import RunDemoRequest, RunDemoResponse
from backend.services import runner

router = APIRouter()


@router.post("/run", response_model=RunDemoResponse)
async def start_demo(body: RunDemoRequest):
    demo_id = runner.new_run_id()
    asyncio.create_task(runner.run_demo(demo_id, body.query, body.weight_profile))
    return RunDemoResponse(demo_id=demo_id)


@router.get("/{demo_id}/stream")
async def stream_demo(demo_id: str, request: Request):
    async def event_generator():
        run = runner.get_run(demo_id)
        if run is None:
            # Wait briefly in case the task hasn't registered yet
            await asyncio.sleep(0.2)
            run = runner.get_run(demo_id)

        if run is None:
            yield {"data": json.dumps({"event": "error", "data": {"message": "demo not found"}})}
            return

        q: asyncio.Queue = run["queue"]
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # Heartbeat keeps the connection alive during long operations
                yield {"data": json.dumps({"event": "heartbeat"})}
                continue

            yield {"data": json.dumps(event)}
            if event.get("event") in ("done", "error"):
                break

    return EventSourceResponse(event_generator())


@router.get("/{demo_id}/results")
async def get_results(demo_id: str):
    run = runner.get_run(demo_id)
    if run is None:
        raise HTTPException(status_code=404, detail="demo not found")
    if run["status"] == "running":
        raise HTTPException(status_code=425, detail="results not ready yet")
    if run["status"] == "error":
        raise HTTPException(status_code=500, detail="demo run failed")
    return run["result"]
