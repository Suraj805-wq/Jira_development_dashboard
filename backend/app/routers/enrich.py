"""Scrape (enrichment) endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..database import get_conn
from ..enrichment.manager import scrape_company

router = APIRouter(prefix="/api", tags=["enrich"])


def _get_company(company_id: int) -> dict:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Company not found")
    return dict(row)


@router.get("/companies/{company_id}/contacts")
def get_contacts(company_id: int, refresh: bool = False):
    """Return scraped contact data, scraping live if not already cached."""
    company = _get_company(company_id)
    return scrape_company(company, force=refresh)


@router.post("/companies/{company_id}/enrich")
def run_enrichment(company_id: int):
    company = _get_company(company_id)
    return scrape_company(company, force=True)


@router.post("/enrich")
def bulk_enrich(
    country: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(25, ge=1, le=500),
    only_unscraped: bool = Query(False),
):
    """Scrape many companies at once (used by the 'Scrape all' button)."""
    conn = get_conn()
    try:
        where, params = ["blocked = 0"], []
        if country:
            where.append("country = ?")
            params.append(country)
        if category:
            where.append("category = ?")
            params.append(category)
        if only_unscraped:
            where.append("id NOT IN (SELECT company_id FROM scrapes)")
        clause = f"WHERE {' AND '.join(where)}"
        rows = conn.execute(
            f"SELECT * FROM companies {clause} ORDER BY employees DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
    finally:
        conn.close()

    done, failed = 0, 0
    for row in rows:
        try:
            res = scrape_company(dict(row), force=True)
            if res["status"] == "failed":
                failed += 1
            else:
                done += 1
        except Exception:
            failed += 1
    return {"processed": done, "failed": failed, "total": len(rows)}
