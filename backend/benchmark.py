"""Cross-country scraper benchmark.

Re-scrapes a representative sample of companies across many countries and
reports per-company + aggregate performance so weak spots can be found.

Usage: python3 benchmark.py [--sample N] [--no-cache]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time

sys.path.insert(0, "/home/user/fleet-leads/backend")

from app.enrichment.scraper import WebScraper  # noqa: E402

DB = "/home/user/fleet-leads/backend/data/fleetleads.db"


def load_companies(limit: int | None = None) -> list[dict]:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    # one company per (country, category) where possible; spread across countries
    rows = conn.execute(
        """SELECT c.*, (SELECT COUNT(*) FROM scrapes s WHERE s.company_id=c.id) AS scraped_before
           FROM companies c
           ORDER BY c.country, c.employees DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def bench_one(scraper: WebScraper, company: dict) -> dict:
    t0 = time.time()
    res = scraper.scrape(company["domain"], company_name=company["name"])
    dt = time.time() - t0
    return {
        "name": company["name"],
        "domain": company["domain"],
        "country": company["country"],
        "category": company["category"],
        "seconds": round(dt, 1),
        "status": res.status,
        "message": (res.message or "")[:70],
        "pages": res.pages_checked,
        "emails": len(res.emails),
        "phones": len(res.phones),
        "people": len(res.people),
        "linkedin_profiles": sum(1 for p in res.people if p.get("linkedin_type") == "profile"),
        "socials": len(res.socials),
        "derived_emails": sum(1 for p in res.people if p.get("email_status") == "pattern-derived"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=24)
    ap.add_argument("--delay", type=float, default=0.5)
    args = ap.parse_args()

    companies = load_companies()
    # pick a spread: sort by country and stride through to cover many countries
    step = max(1, len(companies) // args.sample)
    sample = companies[::step][:args.sample]
    # ensure a few high-value ones are included
    priority = ["samsara.com", "geotab.com", "uffizio.com", "quartix.com",
                "loconav.com", "trackunit.com", "webfleet.com", "eroad.com",
                "concox.com", "octotelematics.com"]
    for dom in priority:
        if not any(c["domain"] == dom for c in sample):
            match = next((c for c in companies if c["domain"] == dom), None)
            if match:
                sample.append(match)

    scraper = WebScraper(respect_robots=True, delay=args.delay, max_pages=10, derive_emails=True)

    print(f"{'Company':26s} {'Country':18s} {'Status':9s} {'s':>5} {'pg':>3} "
          f"{'em':>3} {'ph':>3} {'ppl':>3} {'LI':>3} {'soc':>3}  msg")
    print("-" * 120)

    results = []
    for c in sample:
        r = bench_one(scraper, c)
        results.append(r)
        print(f"{r['name'][:26]:26s} {r['country'][:18]:18s} {r['status']:9s} {r['seconds']:5.1f} "
              f"{r['pages']:3d} {r['emails']:3d} {r['phones']:3d} {r['people']:3d} "
              f"{r['linkedin_profiles']:3d} {r['socials']:3d}  {r['message']}")
        sys.stdout.flush()

    # aggregate
    n = len(results)
    ok = sum(1 for r in results if r["status"] == "ok")
    partial = sum(1 for r in results if r["status"] == "partial")
    failed = sum(1 for r in results if r["status"] == "failed")
    avg_t = sum(r["seconds"] for r in results) / n
    tot = lambda k: sum(r[k] for r in results)
    print("\n" + "=" * 120)
    print(f"AGGREGATE  n={n}  ok={ok}  partial={partial}  failed={failed}  "
          f"success_rate={(ok + partial) / n * 100:.0f}%  avg_time={avg_t:.1f}s")
    print(f"  totals -> emails={tot('emails')} phones={tot('phones')} people={tot('people')} "
          f"linkedin_profiles={tot('linkedin_profiles')} socials={tot('socials')} "
          f"derived_emails={tot('derived_emails')}")
    print("\nFailed companies:")
    for r in results:
        if r["status"] == "failed":
            print(f"  - {r['name']} ({r['domain']}) [{r['country']}]: {r['message']}")


if __name__ == "__main__":
    main()
