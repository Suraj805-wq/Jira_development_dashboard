"""Country discovery endpoint — "target a country, gather its organisations".

POST /api/discover  {"country": "Germany", "scrape": true}
  -> searches for fleet/telematics orgs in that country (free web search),
     verifies each candidate's homepage is actually fleet/telematics,
     adds new ones to the directory, and optionally scrapes them.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .. import blocklist as blocklist_mod
from ..database import get_conn
from ..discovery import DiscoveryEngine
from ..enrichment.manager import scrape_company

router = APIRouter(prefix="/api", tags=["discover"])

COUNTRY_CODES = {
    "united states": "US", "usa": "US", "united kingdom": "GB", "uk": "GB",
    "germany": "DE", "france": "FR", "netherlands": "NL", "belgium": "BE",
    "spain": "ES", "italy": "IT", "portugal": "PT", "poland": "PL",
    "sweden": "SE", "norway": "NO", "denmark": "DK", "finland": "FI",
    "switzerland": "CH", "austria": "AT", "ireland": "IE", "czech republic": "CZ",
    "czechia": "CZ", "romania": "RO", "hungary": "HU", "greece": "GR",
    "turkey": "TR", "israel": "IL", "russia": "RU", "ukraine": "UA",
    "india": "IN", "pakistan": "PK", "bangladesh": "BD", "sri lanka": "LK",
    "nepal": "NP", "china": "CN", "japan": "JP", "south korea": "KR",
    "taiwan": "TW", "hong kong": "HK", "singapore": "SG", "malaysia": "MY",
    "indonesia": "ID", "thailand": "TH", "vietnam": "VN", "philippines": "PH",
    "australia": "AU", "new zealand": "NZ", "canada": "CA", "mexico": "MX",
    "brazil": "BR", "argentina": "AR", "chile": "CL", "colombia": "CO",
    "peru": "PE", "uruguay": "UY", "south africa": "ZA", "nigeria": "NG",
    "kenya": "KE", "egypt": "EG", "morocco": "MA", "tunisia": "TN",
    "ghana": "GH", "united arab emirates": "AE", "uae": "AE", "saudi arabia": "SA",
    "qatar": "QA", "oman": "OM", "kuwait": "KW", "bahrain": "BH",
    "jordan": "JO", "lebanon": "LB", "lithuania": "LT", "latvia": "LV",
    "estonia": "EE", "bulgaria": "BG", "croatia": "HR", "serbia": "RS",
    "slovakia": "SK", "slovenia": "SI", "luxembourg": "LU", "iceland": "IS",
    "malta": "MT", "cyprus": "CY",
}


class DiscoverIn(BaseModel):
    country: str
    scrape: bool = True
    max_domains: int = 25


@router.post("/discover")
def discover_country(body: DiscoverIn):
    country = body.country.strip()
    if not country:
        return {"error": "Country name required."}

    engine = DiscoveryEngine(delay=2.5)
    result = engine.discover(country, max_domains=body.max_domains, verify=True)

    country_code = COUNTRY_CODES.get(country.lower(), "ZZ")
    conn = get_conn()
    added, skipped, scraped_ok, scraped_fail, blocked_skipped = [], [], 0, 0, []
    try:
        for domain, title in result["domains"].items():
            exists = conn.execute(
                "SELECT id, name, blocked FROM companies WHERE domain = ?", (domain,)
            ).fetchone()
            if exists:
                skipped.append({"domain": domain, "name": exists["name"]})
                continue
            name = _derive_name(title, domain)
            if blocklist_mod.is_blocked_candidate(name, domain):
                blocked_skipped.append({"domain": domain, "name": name})
                continue
            cur = conn.execute(
                """INSERT INTO companies
                   (name, domain, website, country, country_code, city, category,
                    description, employees, founded, linkedin_url, tags)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (name, domain, f"https://www.{domain}", country, country_code, None,
                 "Fleet Management Software",
                 f"{name} — discovered via country search for {country}.",
                 None, None, None, "discovered"),
            )
            company_id = cur.lastrowid
            added.append({"domain": domain, "name": name, "id": company_id})
        conn.commit()
    finally:
        conn.close()

    scraped = []
    if body.scrape:
        for item in added:
            conn = get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM companies WHERE id = ?", (item["id"],)
                ).fetchone()
            finally:
                conn.close()
            try:
                res = scrape_company(dict(row), force=True)
                if res["status"] == "failed":
                    scraped_fail += 1
                else:
                    scraped_ok += 1
                scraped.append({
                    "domain": item["domain"],
                    "status": res["status"],
                    "emails": len(res["emails"]),
                    "phones": len(res["phones"]),
                    "people": len(res["people"]),
                })
            except Exception:
                scraped_fail += 1

    return {
        "country": country,
        "sources_used": result.get("sources_used", []),
        "searched_queries": result["queries_run"],
        "candidates_found": len(result["domains"]) + len(result["rejected"]),
        "verified": len(result["domains"]),
        "rejected": [
            {"domain": d, "reason": r} for d, r in list(result["rejected"].items())[:30]
        ],
        "added": added,
        "skipped_existing": skipped,
        "skipped_blocked": blocked_skipped,
        "scraped": scraped,
        "scrape_summary": {"ok": scraped_ok, "failed": scraped_fail},
    }


def _derive_name(title: str, domain: str) -> str:
    """Make a clean company name from a search-result title or the domain."""
    t = (title or "").strip()
    # drop known noise suffixes
    for marker in (" - ", " | ", " – "):
        if marker in t:
            t = t.split(marker)[0].strip()
    if t and 3 <= len(t) <= 60 and " " in t:
        return t
    # fallback: prettify the domain
    base = domain.split(".")[0].replace("-", " ").replace("_", " ")
    return base.title()
