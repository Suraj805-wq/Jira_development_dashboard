"""CSV export of scraped contact data."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ..database import get_conn

router = APIRouter(prefix="/api/export", tags=["export"])

COLUMNS = [
    "Company", "Domain", "Country", "Category", "City", "Type",
    "Value", "Detail", "Source URL",
]


def _company_filter(q: str | None, country: str | None, category: str | None):
    where, params = ["c.blocked = 0"], []
    if country:
        where.append("c.country = ?")
        params.append(country)
    if category:
        where.append("c.category = ?")
        params.append(category)
    if q:
        like = f"%{q}%"
        where.append("(c.name LIKE ? OR c.domain LIKE ?)")
        params.extend([like, like])
    return (" AND ".join(where), params)


@router.get("/contacts")
def export_contacts(
    country: str | None = Query(None),
    category: str | None = Query(None),
    q: str | None = Query(None),
):
    conn = get_conn()
    try:
        clause, params = _company_filter(q, country, category)
        where = f"WHERE {clause}" if clause else ""

        emails = conn.execute(
            f"""SELECT c.name, c.domain, c.country, c.category, c.city,
                       'email' AS type, e.email AS value, e.category AS detail, e.source_url
                FROM emails e JOIN companies c ON c.id = e.company_id {where}""",
            params,
        ).fetchall()
        phones = conn.execute(
            f"""SELECT c.name, c.domain, c.country, c.category, c.city,
                       'phone' AS type, p.phone AS value, p.label AS detail, p.source_url
                FROM phones p JOIN companies c ON c.id = p.company_id {where}""",
            params,
        ).fetchall()
        people = conn.execute(
            f"""SELECT c.name, c.domain, c.country, c.category, c.city,
                       'person' AS type, pe.name AS value, pe.title AS detail, pe.source_url
                FROM people pe JOIN companies c ON c.id = pe.company_id {where}""",
            params,
        ).fetchall()
        socials = conn.execute(
            f"""SELECT c.name, c.domain, c.country, c.category, c.city,
                       'social' AS type, s.url AS value, s.network AS detail, s.url AS source_url
                FROM socials s JOIN companies c ON c.id = s.company_id {where}""",
            params,
        ).fetchall()
    finally:
        conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(COLUMNS)
    for r in [*emails, *phones, *people, *socials]:
        writer.writerow([
            r["name"], r["domain"], r["country"], r["category"], r["city"],
            r["type"], r["value"], r["detail"], r["source_url"],
        ])
    buf.seek(0)

    filename = "fleet-contact-data.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
