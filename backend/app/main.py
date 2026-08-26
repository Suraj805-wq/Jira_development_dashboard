"""FleetLeads — fleet/telematics decision-maker enrichment app.

Run:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .blocklist import apply_blocklist, clear_legacy_defaults
from .database import init_db
from .routers import blocklist, companies, discover, enrich, export, settings, verify, worker
from .seed_data import seed_companies


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    seed_companies()
    clear_legacy_defaults()
    apply_blocklist()
    from .worker import get_worker

    get_worker().start()
    yield
    get_worker().stop()


app = FastAPI(
    title="FleetLeads",
    description="Find fleet-management & telematics organisations and their decision makers.",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies.router)
app.include_router(discover.router)
app.include_router(enrich.router)
app.include_router(settings.router)
app.include_router(export.router)
app.include_router(verify.router)
app.include_router(blocklist.router)
app.include_router(worker.router)


@app.get("/api/health")
def health():
    from .worker import get_worker

    w = get_worker()
    return {"status": "ok", "app": "FleetLeads", "worker": w.running}


FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (
            "<h1>FleetLeads API is running</h1>"
            "<p>The frontend build was not found. Run <code>npm run build</code> in "
            "<code>frontend/</code>, or use the <code>/api</code> endpoints directly.</p>"
            "<p>Docs: <a href='/docs'>/docs</a></p>"
        )
