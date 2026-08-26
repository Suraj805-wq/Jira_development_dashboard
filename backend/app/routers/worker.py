"""Worker control endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from ..worker import get_worker, worker_status

router = APIRouter(prefix="/api/worker", tags=["worker"])


@router.get("/status")
def status():
    return worker_status()


@router.post("/start")
def start():
    get_worker().start()
    return worker_status()


@router.post("/stop")
def stop():
    get_worker().stop()
    return worker_status()
