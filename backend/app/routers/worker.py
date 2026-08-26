"""Worker control endpoints — live discovery thread + activity feed."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..database import worker_log_tail
from ..worker import get_worker, worker_status

router = APIRouter(prefix="/api/worker", tags=["worker"])


@router.get("/status")
def status():
    return worker_status()


@router.get("/log")
def log(limit: int = Query(80, ge=1, le=300)):
    return {"items": worker_log_tail(limit)}


@router.post("/start")
def start():
    get_worker().start()
    return worker_status()


@router.post("/stop")
def stop():
    get_worker().stop()
    return worker_status()


@router.post("/run-now")
def run_now():
    """Wake the thread immediately (or start it) so a cycle begins now."""
    get_worker().wake()
    return worker_status()
