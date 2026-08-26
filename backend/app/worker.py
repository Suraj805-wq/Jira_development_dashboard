"""Continuous background worker — keeps the data warehouse growing.

Runs a polite, never-ending loop that cycles through these jobs (in priority
order, one batch per cycle):

1. DISCOVER   — find new fleet/telematics organisations in the countries that
                currently have the fewest companies.
2. SCRAPE     — scrape organisations that haven't been scraped yet.
3. PEOPLE     — re-scrape organisations that have 0 decision makers (deeper
                look for leadership/team pages).
4. VERIFY     — re-verify emails that are unverified / unknown / rejected so
                every stored address ends up correct.

State (activity, counters) is persisted in `worker_state` so it survives
restarts, and exposed via GET /api/worker/status.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone

from .database import get_conn, worker_get, worker_set
from .discovery import DiscoveryEngine
from .enrichment.manager import scrape_company
from .enrichment.verify import verify_email

MIN_COMPANIES_PER_COUNTRY = 8      # discovery targets countries below this
DISCOVER_BATCH = 1                 # one country per discovery cycle (slow, polite)
SCRAPE_BATCH = 3
PEOPLE_BATCH = 3
VERIFY_BATCH = 12
CYCLE_SLEEP = 60                   # seconds between cycles


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _snapshot() -> dict:
    """Overall warehouse counts (for the status display)."""
    conn = get_conn()
    try:
        return {
            "companies": conn.execute("SELECT COUNT(*) c FROM companies WHERE blocked=0").fetchone()["c"],
            "countries": conn.execute("SELECT COUNT(DISTINCT country) c FROM companies WHERE blocked=0").fetchone()["c"],
            "people": conn.execute("SELECT COUNT(*) c FROM people p JOIN companies c ON c.id=p.company_id WHERE c.blocked=0").fetchone()["c"],
            "verified_people": conn.execute("SELECT COUNT(*) c FROM people p JOIN companies c ON c.id=p.company_id WHERE p.email_status='verified' AND c.blocked=0").fetchone()["c"],
            "emails": conn.execute("SELECT COUNT(*) c FROM emails e JOIN companies c ON c.id=e.company_id WHERE c.blocked=0").fetchone()["c"],
            "verified_emails": conn.execute("SELECT COUNT(*) c FROM emails e JOIN companies c ON c.id=e.company_id WHERE e.verdict='deliverable' AND c.blocked=0").fetchone()["c"],
            "unscraped": conn.execute("SELECT COUNT(*) c FROM companies c WHERE c.blocked=0 AND c.id NOT IN (SELECT company_id FROM scrapes)").fetchone()["c"],
            "zero_people": conn.execute("SELECT COUNT(*) c FROM companies c WHERE c.blocked=0 AND (SELECT COUNT(*) FROM people p WHERE p.company_id=c.id)=0").fetchone()["c"],
        }
    finally:
        conn.close()


def _underrepresented_countries() -> list[str]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT country, COUNT(*) c FROM companies
               WHERE blocked=0 AND country != 'Unknown'
               GROUP BY country HAVING c < ?
               ORDER BY c ASC LIMIT 5""",
            (MIN_COMPANIES_PER_COUNTRY,),
        ).fetchall()
        return [r["country"] for r in rows]
    finally:
        conn.close()


def _job_discover() -> dict:
    countries = _underrepresented_countries()
    if not countries:
        return {"skipped": "no underrepresented countries"}
    country = countries[0]
    engine = DiscoveryEngine(delay=2.0)
    res = engine.discover(country, max_domains=20, verify=True)

    conn = get_conn()
    added = 0
    try:
        for domain, title in res["domains"].items():
            exists = conn.execute(
                "SELECT id FROM companies WHERE domain = ?", (domain,)
            ).fetchone()
            if exists:
                continue
            from .routers.discover import _derive_name
            name = _derive_name(title, domain)
            conn.execute(
                """INSERT OR IGNORE INTO companies
                   (name, domain, website, country, country_code, city, category,
                    description, employees, founded, linkedin_url, tags)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (name, domain, f"https://www.{domain}", country, "ZZ", None,
                 "Fleet Management Software",
                 f"{name} — discovered by the background worker for {country}.",
                 None, None, None, "discovered"),
            )
            added += 1
        conn.commit()
    finally:
        conn.close()
    return {"country": country, "verified_candidates": len(res["domains"]), "added": added}


def _job_scrape() -> dict:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM companies c WHERE c.blocked=0
               AND c.id NOT IN (SELECT company_id FROM scrapes)
               ORDER BY c.employees DESC LIMIT ?""",
            (SCRAPE_BATCH,),
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
    return {"scraped": done, "failed": failed}


def _job_people() -> dict:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT c.* FROM companies c WHERE c.blocked=0
               AND (SELECT COUNT(*) FROM people p WHERE p.company_id=c.id)=0
               ORDER BY c.employees DESC LIMIT ?""",
            (PEOPLE_BATCH,),
        ).fetchall()
    finally:
        conn.close()
    found = 0
    for row in rows:
        try:
            res = scrape_company(dict(row), force=True)
            found += len(res["people"])
        except Exception:
            pass
    return {"rescraped": len(rows), "people_found": found}


def _job_verify() -> dict:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT email FROM emails WHERE verdict IS NULL OR verdict NOT IN ('deliverable')
               LIMIT ?""",
            (VERIFY_BATCH,),
        ).fetchall()
    finally:
        conn.close()
    fixed = 0
    conn = get_conn()
    try:
        for r in rows:
            email = r["email"]
            v = verify_email(email, timeout=8)
            conn.execute(
                """UPDATE emails SET mx_status=?, smtp_status=?, catchall=?, verdict=?,
                   disposable=?, verified_at=? WHERE email=?""",
                (v["mx_status"], v["smtp_status"], v["catchall"], v["verdict"],
                 "yes" if v["disposable"] else "no", _now(), email),
            )
            if v["verdict"] == "deliverable":
                fixed += 1
        conn.commit()
    finally:
        conn.close()
    return {"checked": len(rows), "now_deliverable": fixed}


class ContinuousWorker:
    def __init__(self, cycle_sleep: int = CYCLE_SLEEP):
        self.cycle_sleep = cycle_sleep
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ #
    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return False
        self._stop.clear()
        worker_set("enabled", "true")
        self._thread = threading.Thread(target=self._run, daemon=True, name="fleetleads-worker")
        self._thread.start()
        return True

    def stop(self) -> bool:
        self._stop.set()
        worker_set("enabled", "false")
        return True

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ------------------------------------------------------------------ #
    def _set_status(self, **fields) -> None:
        worker_set("status_json", json.dumps({**fields, "updated_at": _now()}))

    def _run(self) -> None:
        worker_set("started_at", _now())
        counters = self._load_counters()
        jobs = [
            ("discover", _job_discover, "discovered"),
            ("scrape", _job_scrape, "scraped"),
            ("people", _job_people, "people_rescraped"),
            ("verify", _job_verify, "verify_batches"),
        ]
        while not self._stop.is_set():
            for name, job, counter_key in jobs:
                if self._stop.is_set():
                    break
                try:
                    self._set_status(activity=name)
                    result = job()
                    counters[counter_key] = counters.get(counter_key, 0) + 1
                    counters["last_result"] = result
                    self._set_status(activity=name, result=result)
                except Exception as exc:
                    self._set_status(activity=name, error=f"{type(exc).__name__}: {exc}")
                time.sleep(3)
            # persist counters + snapshot
            counters["snapshot"] = _snapshot()
            worker_set("counters", json.dumps(counters))
            # sleep the remainder of the cycle
            for _ in range(self.cycle_sleep):
                if self._stop.is_set():
                    break
                time.sleep(1)
        worker_set("stopped_at", _now())

    @staticmethod
    def _load_counters() -> dict:
        raw = worker_get("counters")
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return {}


_WORKER = ContinuousWorker()


def get_worker() -> ContinuousWorker:
    return _WORKER


def worker_status() -> dict:
    """Status for the UI/API."""
    raw = worker_get("status_json") or "{}"
    try:
        status = json.loads(raw)
    except json.JSONDecodeError:
        status = {}
    counters = _WORKER._load_counters()
    return {
        "running": _WORKER.running,
        "enabled": worker_get("enabled") == "true",
        "activity": status.get("activity"),
        "last_result": status.get("last_result") or counters.get("last_result"),
        "error": status.get("error"),
        "updated_at": status.get("updated_at"),
        "started_at": worker_get("started_at"),
        "counters": counters,
        "snapshot": _snapshot(),
    }
