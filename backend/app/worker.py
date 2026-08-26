"""Continuous background worker — keeps the data warehouse growing.

A dedicated daemon thread cycles forever through:

1. DISCOVER  — find new fleet/telematics organisations (under-covered + expansion countries)
2. SCRAPE    — scrape organisations that haven't been scraped yet
3. PEOPLE    — re-scrape organisations that still have 0 decision makers
4. VERIFY    — re-verify emails that are still unchecked

Every step writes to `worker_log` so the dashboard can show a live activity
feed, thread identity, pipeline remaining, and session counters.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone

from .database import get_conn, worker_get, worker_log, worker_log_tail, worker_set
from .discovery import DiscoveryEngine
from .enrichment.manager import scrape_company
from .enrichment.verify import verify_email

MIN_COMPANIES_PER_COUNTRY = 8
DISCOVER_BATCH = 1
SCRAPE_BATCH = 2
PEOPLE_BATCH = 2
VERIFY_BATCH = 8
CYCLE_SLEEP = 12

# Countries the worker will try even if they are not in the seed directory yet.
EXPANSION_COUNTRIES = [
    "Kenya", "Nigeria", "Vietnam", "Thailand", "Romania", "Hungary",
    "Philippines", "Argentina", "Peru", "Egypt", "Ghana", "Qatar",
    "Kuwait", "Oman", "Bahrain", "Jordan", "Czech Republic", "Austria",
    "Greece", "Portugal", "Chile", "Colombia", "Indonesia", "Malaysia",
]

COUNTRY_CODES = {
    "united states": "US", "usa": "US", "united kingdom": "GB", "uk": "GB",
    "germany": "DE", "france": "FR", "netherlands": "NL", "belgium": "BE",
    "spain": "ES", "italy": "IT", "portugal": "PT", "poland": "PL",
    "sweden": "SE", "norway": "NO", "denmark": "DK", "finland": "FI",
    "switzerland": "CH", "austria": "AT", "ireland": "IE", "czech republic": "CZ",
    "czechia": "CZ", "romania": "RO", "hungary": "HU", "greece": "GR",
    "turkey": "TR", "israel": "IL", "india": "IN", "china": "CN", "japan": "JP",
    "south korea": "KR", "taiwan": "TW", "hong kong": "HK", "singapore": "SG",
    "malaysia": "MY", "indonesia": "ID", "thailand": "TH", "vietnam": "VN",
    "philippines": "PH", "australia": "AU", "new zealand": "NZ", "canada": "CA",
    "mexico": "MX", "brazil": "BR", "argentina": "AR", "chile": "CL",
    "colombia": "CO", "peru": "PE", "south africa": "ZA", "nigeria": "NG",
    "kenya": "KE", "egypt": "EG", "morocco": "MA", "ghana": "GH",
    "united arab emirates": "AE", "uae": "AE", "saudi arabia": "SA",
    "qatar": "QA", "oman": "OM", "kuwait": "KW", "bahrain": "BH",
    "jordan": "JO", "lithuania": "LT", "latvia": "LV", "estonia": "EE",
    "bulgaria": "BG", "croatia": "HR", "slovakia": "SK", "slovenia": "SI",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _snapshot() -> dict:
    conn = get_conn()
    try:
        def q(sql: str) -> int:
            return conn.execute(sql).fetchone()[0]

        unscraped = q(
            "SELECT COUNT(*) FROM companies c WHERE c.blocked=0 "
            "AND c.id NOT IN (SELECT company_id FROM scrapes)"
        )
        zero_people = q(
            "SELECT COUNT(*) FROM companies c WHERE c.blocked=0 "
            "AND (SELECT COUNT(*) FROM people p WHERE p.company_id=c.id)=0"
        )
        pending_verify = q(
            "SELECT COUNT(*) FROM emails e JOIN companies c ON c.id=e.company_id "
            "WHERE c.blocked=0 AND (e.verdict IS NULL OR e.verdict NOT IN "
            "('deliverable','catchall','rejected','invalid','disposable'))"
        )
        companies = q("SELECT COUNT(*) FROM companies WHERE blocked=0")
        return {
            "companies": companies,
            "countries": q("SELECT COUNT(DISTINCT country) FROM companies WHERE blocked=0"),
            "people": q(
                "SELECT COUNT(*) FROM people p JOIN companies c ON c.id=p.company_id WHERE c.blocked=0"
            ),
            "verified_people": q(
                "SELECT COUNT(*) FROM people p JOIN companies c ON c.id=p.company_id "
                "WHERE p.email_status='verified' AND c.blocked=0"
            ),
            "derived_people": q(
                "SELECT COUNT(*) FROM people p JOIN companies c ON c.id=p.company_id "
                "WHERE p.email_status='pattern-derived' AND c.blocked=0"
            ),
            "published_people": q(
                "SELECT COUNT(*) FROM people p JOIN companies c ON c.id=p.company_id "
                "WHERE p.email_status='published' AND c.blocked=0"
            ),
            "emails": q(
                "SELECT COUNT(*) FROM emails e JOIN companies c ON c.id=e.company_id WHERE c.blocked=0"
            ),
            "verified_emails": q(
                "SELECT COUNT(*) FROM emails e JOIN companies c ON c.id=e.company_id "
                "WHERE e.verdict='deliverable' AND c.blocked=0"
            ),
            "unscraped": unscraped,
            "zero_people": zero_people,
            "pending_verify": pending_verify,
            "pipeline": {
                "scrape_remaining": unscraped,
                "people_remaining": zero_people,
                "verify_remaining": pending_verify,
            },
        }
    finally:
        conn.close()


class ContinuousWorker:
    def __init__(self, cycle_sleep: int = CYCLE_SLEEP):
        self.cycle_sleep = cycle_sleep
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._cycle = 0
        self._activity_started: str | None = None
        self._last_activity: str | None = None
        self._detail = ""

    def start(self) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop.clear()
            self._wake.clear()
            worker_set("enabled", "true")
            self._thread = threading.Thread(
                target=self._run, daemon=True, name="fleetleads-discovery"
            )
            self._thread.start()
        worker_log("system", "Discovery thread started", "success", {
            "thread": self._thread.name if self._thread else None,
            "ident": self._thread.ident if self._thread else None,
        })
        return True

    def stop(self) -> bool:
        self._stop.set()
        self._wake.set()
        worker_set("enabled", "false")
        worker_log("system", "Discovery thread pause requested", "warn")
        return True

    def wake(self) -> None:
        """Skip the idle sleep and run the next cycle immediately."""
        self._wake.set()
        if not self.running:
            self.start()
        worker_log("system", "Run-now: waking discovery thread", "info")

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def _set_status(self, activity: str, detail: str = "", result=None, error: str | None = None) -> None:
        if activity != self._last_activity:
            self._activity_started = _now()
            self._last_activity = activity
        self._detail = detail
        worker_set("heartbeat", _now())
        payload = {
            "activity": activity,
            "detail": detail,
            "activity_started_at": self._activity_started or _now(),
            "cycle": self._cycle,
            "result": result,
            "error": error,
            "updated_at": _now(),
        }
        worker_set("status_json", json.dumps(payload))

    def _run(self) -> None:
        worker_set("started_at", _now())
        worker_set("heartbeat", _now())
        counters = self._load_counters()
        jobs = [
            ("discover", self._job_discover, "discovered"),
            ("scrape", self._job_scrape, "scraped"),
            ("people", self._job_people, "people_rescraped"),
            ("verify", self._job_verify, "verify_batches"),
        ]
        while not self._stop.is_set():
            self._cycle += 1
            counters["cycles"] = self._cycle
            worker_log("system", f"Cycle {self._cycle} started", "info")
            for name, job, counter_key in jobs:
                if self._stop.is_set():
                    break
                try:
                    self._set_status(name, f"Running {name} job")
                    result = job()
                    counters[counter_key] = counters.get(counter_key, 0) + 1
                    counters["last_result"] = result
                    self._set_status(name, result.get("summary") or f"{name} finished", result=result)
                except Exception as exc:
                    self._set_status(name, f"{type(exc).__name__}: {exc}", error=f"{type(exc).__name__}: {exc}")
                    worker_log(name, f"{name} failed: {type(exc).__name__}: {exc}", "error")
                time.sleep(1)
            counters["snapshot"] = _snapshot()
            worker_set("counters", json.dumps(counters))
            self._set_status("idle", f"Sleeping {self.cycle_sleep}s until next cycle")
            worker_log("system", f"Cycle {self._cycle} complete — sleeping {self.cycle_sleep}s", "info")
            self._sleep_or_wake(self.cycle_sleep)
        worker_set("stopped_at", _now())
        worker_log("system", "Discovery thread stopped", "warn")

    def _sleep_or_wake(self, seconds: int) -> None:
        self._wake.clear()
        for _ in range(max(1, seconds)):
            if self._stop.is_set() or self._wake.is_set():
                break
            time.sleep(1)
            worker_set("heartbeat", _now())
        self._wake.clear()

    def _next_discover_country(self) -> str | None:
        conn = get_conn()
        try:
            under = conn.execute(
                """SELECT country, COUNT(*) c FROM companies
                   WHERE blocked=0 AND country != 'Unknown'
                   GROUP BY country HAVING c < ?
                   ORDER BY c ASC LIMIT 1""",
                (MIN_COMPANIES_PER_COUNTRY,),
            ).fetchone()
            if under:
                return under["country"]
            existing = {
                r["country"] for r in conn.execute(
                    "SELECT DISTINCT country FROM companies WHERE blocked=0"
                ).fetchall()
            }
        finally:
            conn.close()

        cursor = int(worker_get("discover_cursor") or "0")
        # Prefer expansion countries not yet in the directory, then rotate all.
        missing = [c for c in EXPANSION_COUNTRIES if c not in existing]
        pool = missing or EXPANSION_COUNTRIES
        country = pool[cursor % len(pool)]
        worker_set("discover_cursor", str(cursor + 1))
        return country

    def _job_discover(self) -> dict:
        country = self._next_discover_country()
        if not country:
            worker_log("discover", "No country to target", "warn")
            return {"skipped": "no country", "summary": "No country to discover"}
        code = COUNTRY_CODES.get(country.lower(), "UN")
        self._set_status("discover", f"Searching fleet organisations in {country}")
        worker_log("discover", f"Discovering organisations in {country}…", "info", {"country": country})
        engine = DiscoveryEngine(delay=1.6)
        res = engine.discover(country, max_domains=16, verify=True)

        from .blocklist import is_blocked_candidate
        from .routers.discover import _derive_name

        conn = get_conn()
        added = 0
        added_names: list[str] = []
        try:
            for domain, title in res["domains"].items():
                exists = conn.execute(
                    "SELECT id FROM companies WHERE domain = ?", (domain,)
                ).fetchone()
                if exists:
                    continue
                name = _derive_name(title, domain)
                if is_blocked_candidate(name, domain):
                    continue
                cur = conn.execute(
                    """INSERT OR IGNORE INTO companies
                       (name, domain, website, country, country_code, city, category,
                        description, employees, founded, linkedin_url, tags)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (name, domain, f"https://{domain}", country, code, None,
                     "Fleet Management Software",
                     f"{name} — discovered in {country} by the background worker.",
                     None, None, None, "discovered"),
                )
                if cur.rowcount:
                    added += 1
                    added_names.append(name)
            conn.commit()
        finally:
            conn.close()

        summary = (
            f"{country}: {len(res['domains'])} verified candidates, "
            f"+{added} new organisations"
        )
        worker_log(
            "discover",
            summary,
            "success" if added else "info",
            {
                "country": country,
                "verified": len(res["domains"]),
                "added": added,
                "names": added_names[:12],
                "sources": res.get("sources_used") or [],
            },
        )
        return {
            "country": country,
            "verified_candidates": len(res["domains"]),
            "added": added,
            "names": added_names,
            "sources": res.get("sources_used") or [],
            "summary": summary,
        }

    def _job_scrape(self) -> dict:
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
        if not rows:
            worker_log("scrape", "No unscraped organisations left", "info")
            return {"scraped": 0, "failed": 0, "summary": "Nothing left to scrape"}
        done, failed = 0, 0
        for row in rows:
            if self._stop.is_set():
                break
            name, domain = row["name"], row["domain"]
            self._set_status("scrape", f"Scraping {name} ({domain})")
            worker_log("scrape", f"Scraping {name}", "info", {"domain": domain})
            try:
                res = scrape_company(dict(row), force=True)
                people = len(res.get("people") or [])
                emails = len(res.get("emails") or [])
                if res["status"] == "failed":
                    failed += 1
                    worker_log("scrape", f"{name} failed: {res.get('message') or 'scrape failed'}", "error")
                else:
                    done += 1
                    worker_log(
                        "scrape",
                        f"{name}: {people} people, {emails} emails ({res['status']})",
                        "success",
                        {"people": people, "emails": emails, "status": res["status"]},
                    )
            except Exception as exc:
                failed += 1
                worker_log("scrape", f"{name} crashed: {exc}", "error")
        summary = f"Scraped {done} organisation(s), {failed} failed"
        return {"scraped": done, "failed": failed, "summary": summary}

    def _job_people(self) -> dict:
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
        if not rows:
            worker_log("people", "Every organisation already has decision makers", "info")
            return {"rescraped": 0, "people_found": 0, "summary": "No empty leadership lists"}
        found = 0
        for row in rows:
            if self._stop.is_set():
                break
            self._set_status("people", f"Finding decision makers at {row['name']}")
            worker_log("people", f"Looking up leadership for {row['name']}", "info")
            try:
                res = scrape_company(dict(row), force=True)
                n = len(res.get("people") or [])
                found += n
                worker_log(
                    "people",
                    f"{row['name']}: {n} decision maker(s)",
                    "success" if n else "warn",
                )
            except Exception as exc:
                worker_log("people", f"{row['name']} failed: {exc}", "error")
        summary = f"Re-scraped {len(rows)} orgs, found {found} people"
        return {"rescraped": len(rows), "people_found": found, "summary": summary}

    def _job_verify(self) -> dict:
        conn = get_conn()
        try:
            rows = conn.execute(
                """SELECT email FROM emails
                   WHERE verdict IS NULL OR verdict NOT IN
                     ('deliverable','catchall','rejected','invalid','disposable')
                   LIMIT ?""",
                (VERIFY_BATCH,),
            ).fetchall()
        finally:
            conn.close()
        if not rows:
            worker_log("verify", "No emails waiting for verification", "info")
            return {"checked": 0, "now_deliverable": 0, "summary": "Verification queue empty"}
        self._set_status("verify", f"Verifying {len(rows)} email(s)")
        fixed = 0
        conn = get_conn()
        try:
            for r in rows:
                if self._stop.is_set():
                    break
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
        summary = f"Checked {len(rows)} emails, {fixed} now deliverable"
        worker_log("verify", summary, "success" if fixed else "info")
        return {"checked": len(rows), "now_deliverable": fixed, "summary": summary}

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
    raw = worker_get("status_json") or "{}"
    try:
        status = json.loads(raw)
    except json.JSONDecodeError:
        status = {}
    counters = _WORKER._load_counters()
    thread = _WORKER._thread
    heartbeat = worker_get("heartbeat")
    return {
        "running": _WORKER.running,
        "enabled": worker_get("enabled") == "true",
        "activity": status.get("activity"),
        "detail": status.get("detail") or _WORKER._detail,
        "activity_started_at": status.get("activity_started_at"),
        "cycle": status.get("cycle") or counters.get("cycles") or 0,
        "last_result": status.get("result") or counters.get("last_result"),
        "error": status.get("error"),
        "updated_at": status.get("updated_at"),
        "heartbeat": heartbeat,
        "started_at": worker_get("started_at"),
        "counters": counters,
        "snapshot": _snapshot(),
        "log": worker_log_tail(60),
        "thread": {
            "alive": bool(thread and thread.is_alive()),
            "name": thread.name if thread else None,
            "ident": thread.ident if thread else None,
            "daemon": True,
        },
    }
