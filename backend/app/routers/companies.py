"""Company directory, country/category facets, on-demand lookup and stats."""
from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .. import blocklist as blocklist_mod
from ..database import get_conn
from ..enrichment.manager import scrape_company
from ..enrichment.scraper import USER_AGENT

router = APIRouter(prefix="/api", tags=["companies"])

DOMAIN_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$")


class LookupIn(BaseModel):
    query: str


def _company_row(row) -> dict:
    d = dict(row)
    d["website"] = d["website"] or f"https://www.{d['domain']}"
    return d


_COUNT_SQL = """
    (SELECT COUNT(*) FROM emails e WHERE e.company_id = c.id) AS email_count,
    (SELECT COUNT(*) FROM phones p WHERE p.company_id = c.id) AS phone_count,
    (SELECT COUNT(*) FROM people pe WHERE pe.company_id = c.id) AS people_count,
    (SELECT COUNT(*) FROM socials s WHERE s.company_id = c.id) AS social_count
"""


@router.get("/companies")
def list_companies(
    country: str | None = Query(None, description="Country name filter"),
    q: str | None = Query(None, description="Search name / domain / city / category"),
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=200),
):
    conn = get_conn()
    try:
        where, params = ["blocked = 0"], []
        if country:
            where.append("country = ?")
            params.append(country)
        if category:
            where.append("category = ?")
            params.append(category)
        if q:
            like = f"%{q}%"
            where.append("(name LIKE ? OR domain LIKE ? OR city LIKE ? OR category LIKE ?)")
            params.extend([like, like, like, like])

        clause = f"WHERE {' AND '.join(where)}"
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM companies {clause}", params
        ).fetchone()["c"]

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""SELECT c.*, {_COUNT_SQL}
                FROM companies c {clause}
                ORDER BY employees DESC, name ASC
                LIMIT ? OFFSET ?""",
            [*params, page_size, offset],
        ).fetchall()

        country_rows = conn.execute(
            """SELECT country, country_code, COUNT(*) AS c FROM companies
               WHERE blocked = 0
               GROUP BY country, country_code ORDER BY c DESC, country"""
        ).fetchall()
        category_rows = conn.execute(
            """SELECT category, COUNT(*) AS c FROM companies
               WHERE blocked = 0
               GROUP BY category ORDER BY c DESC"""
        ).fetchall()
    finally:
        conn.close()

    return {
        "items": [_company_row(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "facets": {
            "countries": [dict(r) for r in country_rows],
            "categories": [dict(r) for r in category_rows],
        },
    }


@router.post("/companies/lookup")
def lookup_company(body: LookupIn):
    """Search ANY company worldwide: resolve its website, add it to the
    directory and scrape it on demand."""
    q = body.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Empty query.")

    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT * FROM companies WHERE lower(name) = lower(?) OR lower(domain) = lower(?)",
            (q, q.lower().lstrip("www.")),
        ).fetchone()
        if existing:
            if existing["blocked"]:
                return {"company": dict(existing), "existing": True, "blocked": True}
            return {"company": dict(existing), "existing": True}
    finally:
        conn.close()

    # Build domain candidates.
    if DOMAIN_RE.match(q) and " " not in q:
        candidates = [q.lower().lstrip("www.")]
    else:
        slug = re.sub(r"[^a-z0-9]+", "", q.lower())
        candidates = [f"{slug}.com", f"{slug}.io", f"{slug}.co", f"{slug}.net", f"{slug}.ai"]

    name_tokens = [t for t in re.split(r"[^A-Za-z0-9]+", q) if len(t) >= 3][:2]

    chosen_domain = None
    chosen_base = None
    best_score = -1.0
    with httpx.Client(follow_redirects=True, timeout=15, headers={"User-Agent": USER_AGENT}) as client:
        for cand in candidates:
            base = _resolve(client, cand)
            if not base:
                continue
            title = _title(client, base)
            score = 0.0
            if name_tokens and any(t.lower() in title.lower() for t in name_tokens):
                score += 2.0
            if cand.endswith(".com"):
                score += 1.0
            elif cand.endswith(".io") or cand.endswith(".ai") or cand.endswith(".org"):
                score += 0.5
            if score > best_score:
                best_score = score
                chosen_domain, chosen_base = cand, base

    if not chosen_domain:
        raise HTTPException(
            status_code=404,
            detail=f"Could not resolve a website for “{q}”. Try entering the exact domain (e.g. company.com).",
        )

    if blocklist_mod.is_blocked_candidate(q, chosen_domain):
        raise HTTPException(
            status_code=403,
            detail=f"“{q}” is on your blocklist — it will not be added.",
        )

    company = {
        "name": q.title(),
        "domain": chosen_domain,
        "website": chosen_base or f"https://www.{chosen_domain}",
        "country": "Unknown",
        "country_code": "ZZ",
        "city": None,
        "category": "Custom Search",
        "description": f"Added on-demand via global search for “{q}”.",
        "employees": None,
        "founded": None,
        "linkedin_url": None,
    }
    conn = get_conn()
    try:
        # Race-safe: another request may have added the same domain.
        dup = conn.execute(
            "SELECT * FROM companies WHERE domain = ?", (chosen_domain,)
        ).fetchone()
        if dup:
            return {"company": dict(dup), "existing": True}
        cur = conn.execute(
            """INSERT INTO companies
               (name, domain, website, country, country_code, city, category,
                description, employees, founded, linkedin_url, tags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (company["name"], company["domain"], company["website"], company["country"],
             company["country_code"], company["city"], company["category"],
             company["description"], company["employees"], company["founded"],
             company["linkedin_url"], "custom"),
        )
        company_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    conn = get_conn()
    try:
        company = dict(conn.execute(
            "SELECT * FROM companies WHERE id = ?", (company_id,)
        ).fetchone())
    finally:
        conn.close()

    result = scrape_company(company, force=True)
    return {"company": company, "result": result, "existing": False}


def _resolve(client: httpx.Client, domain: str) -> str | None:
    """Return the resolved URL if the domain hosts a live site.

    403/429 still count as "live" — the domain exists but is bot-protected.
    """
    for cand in (f"https://{domain}", f"https://www.{domain}", f"http://{domain}"):
        try:
            r = client.get(cand)
            if r.status_code < 400 or r.status_code in (401, 403, 429):
                return str(r.url).rstrip("/") or cand
        except httpx.HTTPError:
            continue
    return None


def _title(client: httpx.Client, base: str) -> str:
    try:
        r = client.get(base)
        soup = BeautifulSoup(r.text, "lxml")
        return soup.title.get_text(" ", strip=True) if soup.title else ""
    except Exception:
        return ""


@router.get("/companies/{company_id}")
def get_company(company_id: int):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM companies WHERE id = ?", (company_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Company not found")
    return _company_row(row)


@router.get("/countries")
def list_countries():
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT country, country_code, COUNT(*) AS c FROM companies
               WHERE blocked = 0
               GROUP BY country, country_code ORDER BY c DESC, country"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/categories")
def list_categories():
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT category, COUNT(*) AS c FROM companies
               WHERE blocked = 0
               GROUP BY category ORDER BY c DESC"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/stats")
def stats():
    conn = get_conn()
    try:
        companies = conn.execute(
            "SELECT COUNT(*) AS c FROM companies WHERE blocked = 0"
        ).fetchone()["c"]
        countries = conn.execute(
            "SELECT COUNT(DISTINCT country) AS c FROM companies WHERE blocked = 0"
        ).fetchone()["c"]
        emails = conn.execute(
            "SELECT COUNT(*) AS c FROM emails e JOIN companies c ON c.id = e.company_id WHERE c.blocked = 0"
        ).fetchone()["c"]
        phones = conn.execute(
            "SELECT COUNT(*) AS c FROM phones p JOIN companies c ON c.id = p.company_id WHERE c.blocked = 0"
        ).fetchone()["c"]
        people = conn.execute(
            "SELECT COUNT(*) AS c FROM people pe JOIN companies c ON c.id = pe.company_id WHERE c.blocked = 0"
        ).fetchone()["c"]
        scraped = conn.execute(
            "SELECT COUNT(*) AS c FROM scrapes s JOIN companies c ON c.id = s.company_id WHERE s.status IN ('ok','partial') AND c.blocked = 0"
        ).fetchone()["c"]
        verified = conn.execute(
            "SELECT (SELECT COUNT(*) FROM emails e JOIN companies c ON c.id=e.company_id WHERE e.smtp_status='deliverable' AND c.blocked=0)"
            " + (SELECT COUNT(*) FROM people pe JOIN companies c ON c.id=pe.company_id WHERE pe.smtp_status='deliverable' AND c.blocked=0) AS c"
        ).fetchone()["c"]
        blocked_count = conn.execute(
            "SELECT COUNT(*) AS c FROM companies WHERE blocked = 1"
        ).fetchone()["c"]
    finally:
        conn.close()
    return {
        "companies": companies,
        "countries": countries,
        "emails": emails,
        "phones": phones,
        "people": people,
        "scraped_companies": scraped,
        "verified": verified,
        "blocked": blocked_count,
    }
