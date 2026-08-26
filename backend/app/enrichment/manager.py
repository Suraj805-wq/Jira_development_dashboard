"""Scrape orchestration + caching + save-time email verification.

Flow for a company:

1. Scrape its website (published emails/phones/socials + decision makers).
2. Determine the company's mail domain (the majority domain among its
   published emails, falling back to the company domain).
3. Verify published emails (MX + SMTP + catch-all) before saving.
4. For every decision maker, try name-based email combinations and verify
   each until one is confirmed deliverable — only then is it saved. If the
   domain is a catch-all, the best-guess combination is kept but flagged
   "catchall" (unconfirmed).
5. Save only correct, verified data.

Results are cached in SQLite and can be force-refreshed.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..database import all_settings, get_conn
from .scraper import WebScraper
from .verify import generate_candidates, verify_candidates, verify_email

DEFAULTS = {
    "RESPECT_ROBOTS": "true",
    "REQUEST_DELAY": "1.0",
    "MAX_PAGES": "10",
    "DERIVE_EMAILS": "true",
    "VERIFY_ON_SAVE": "true",
    "SMTP_TIMEOUT": "8",
    "MAX_EMAIL_CANDIDATES": "11",
    "FIND_NAMES_WEB": "true",
}


def scraper_config() -> tuple[WebScraper, dict]:
    settings = all_settings()
    respect = settings.get("RESPECT_ROBOTS", DEFAULTS["RESPECT_ROBOTS"]).lower() != "false"
    derive = settings.get("DERIVE_EMAILS", DEFAULTS["DERIVE_EMAILS"]).lower() != "false"
    try:
        delay = float(settings.get("REQUEST_DELAY", DEFAULTS["REQUEST_DELAY"]))
    except ValueError:
        delay = 1.0
    try:
        max_pages = int(settings.get("MAX_PAGES", DEFAULTS["MAX_PAGES"]))
    except ValueError:
        max_pages = 10
    from ..netclient import parse_proxies

    proxies = parse_proxies(settings.get("PROXY_URL"))
    scraper = WebScraper(
        respect_robots=respect, delay=delay, max_pages=max_pages,
        derive_emails=derive, proxies=proxies,
    )
    return scraper, settings


def _verify_settings(settings: dict[str, str]) -> dict:
    verify_on_save = settings.get("VERIFY_ON_SAVE", DEFAULTS["VERIFY_ON_SAVE"]).lower() != "false"
    try:
        smtp_timeout = int(settings.get("SMTP_TIMEOUT", DEFAULTS["SMTP_TIMEOUT"]))
    except ValueError:
        smtp_timeout = 8
    try:
        max_candidates = int(settings.get("MAX_EMAIL_CANDIDATES", DEFAULTS["MAX_EMAIL_CANDIDATES"]))
    except ValueError:
        max_candidates = 11
    return {
        "verify_on_save": verify_on_save,
        "smtp_timeout": smtp_timeout,
        "max_candidates": max_candidates,
    }


def _majority_mail_domain(result) -> str:
    """The domain most of a company's published emails share (its real mail domain)."""
    from collections import Counter

    domains = [e["email"].split("@")[-1].lower() for e in result.emails]
    if not domains:
        return result.domain
    return Counter(domains).most_common(1)[0][0]


def _verify_and_finalize(result, settings: dict[str, str]) -> None:
    """Verify emails (published + derived) and keep only correct ones.

    Mutates `result` in place:
      - each published email gets verdict/mx_status/smtp_status/catchall
      - each person's email is verified; if rejected, alternative name-based
        combinations are tried until one is deliverable
    """
    cfg = _verify_settings(settings)
    if not cfg["verify_on_save"]:
        for p in result.people:
            p["email_status"] = p.get("email_status") or "unverified"
        return

    timeout = cfg["smtp_timeout"]
    mail_domain = _majority_mail_domain(result)

    # --- verify published emails ------------------------------------- #
    for e in result.emails:
        v = verify_email(e["email"], timeout=timeout)
        e["verdict"] = v["verdict"]
        e["mx_status"] = v["mx_status"]
        e["smtp_status"] = v["smtp_status"]
        e["catchall"] = v["catchall"]
        e["disposable"] = "yes" if v["disposable"] else "no"

    # --- verify / correct decision-maker emails ----------------------- #
    for person in result.people:
        name = person.get("name") or ""
        existing = (person.get("email") or "").lower()

        # 1) If the person has a published/derived email, verify it.
        if existing:
            v = verify_email(existing, timeout=timeout)
            person["mx_status"] = v["mx_status"]
            person["smtp_status"] = v["smtp_status"]
            person["catchall"] = v["catchall"]
            person["disposable"] = "yes" if v["disposable"] else "no"
            if v["verdict"] == "deliverable":
                person["email_status"] = "verified"
                continue
            if v["verdict"] == "catchall":
                person["email_status"] = "catchall"
                continue
            # rejected / invalid / disposable -> discard and try alternatives
            if v["verdict"] in ("rejected", "invalid", "disposable"):
                person["email"] = None
                person["email_status"] = None
                person["mx_status"] = None
                person["smtp_status"] = None
                person["catchall"] = None
                person["disposable"] = None

        # 2) Try name-based combinations until one verifies.
        if not person.get("email"):
            candidates = generate_candidates(name, mail_domain)[: cfg["max_candidates"]]
            if candidates:
                res = verify_candidates(candidates, timeout=timeout)
                if res["winner"]:
                    person["email"] = res["winner"]
                    if res["winner_verdict"] == "deliverable":
                        person["email_status"] = "verified"
                    elif res["winner_verdict"] == "catchall":
                        person["email_status"] = "catchall"
                    else:
                        person["email_status"] = res["winner_verdict"] or "unverified"
                    v = verify_email(res["winner"], timeout=timeout)
                    person["mx_status"] = v["mx_status"]
                    person["smtp_status"] = v["smtp_status"]
                    person["catchall"] = v["catchall"]
                else:
                    # nothing deliverable — do not save a guessed email
                    person["email"] = None
                    person["email_status"] = "none-verified"


def cached_result(company_id: int) -> dict[str, Any]:
    conn = get_conn()
    try:
        scrape = conn.execute(
            "SELECT * FROM scrapes WHERE company_id = ?", (company_id,)
        ).fetchone()
        emails = [dict(r) for r in conn.execute(
            "SELECT * FROM emails WHERE company_id = ? ORDER BY category, email", (company_id,)
        ).fetchall()]
        phones = [dict(r) for r in conn.execute(
            "SELECT * FROM phones WHERE company_id = ?", (company_id,)
        ).fetchall()]
        socials = [dict(r) for r in conn.execute(
            "SELECT * FROM socials WHERE company_id = ? ORDER BY network", (company_id,)
        ).fetchall()]
        people = [dict(r) for r in conn.execute(
            "SELECT * FROM people WHERE company_id = ?", (company_id,)
        ).fetchall()]
    finally:
        conn.close()

    return {
        "company_id": company_id,
        "scraped": scrape is not None,
        "status": scrape["status"] if scrape else None,
        "message": scrape["message"] if scrape else None,
        "pages_checked": scrape["pages_checked"] if scrape else 0,
        "base_url": scrape["base_url"] if scrape else None,
        "scraped_at": scrape["scraped_at"] if scrape else None,
        "emails": emails,
        "phones": phones,
        "socials": socials,
        "people": people,
    }


def _store(company_id: int, result) -> None:
    """Merge scrape results into the DB (upsert by natural key).

    IMPORTANT: never deletes existing rows. A re-scrape only ADDS or UPDATES
    records. If a re-scrape transiently fails (rate-limit, site down), the
    previously saved data is preserved — nothing is lost.
    """
    conn = get_conn()
    try:
        for e in result.emails:
            conn.execute(
                """INSERT INTO emails
                   (company_id, email, category, source_url, mx_status, smtp_status,
                    disposable, catchall, verdict, verified_at)
                   VALUES (?,?,?,?,?,?,?,?,?, datetime('now'))
                   ON CONFLICT(company_id, email) DO UPDATE SET
                     category=excluded.category,
                     source_url=COALESCE(excluded.source_url, emails.source_url),
                     mx_status=COALESCE(excluded.mx_status, emails.mx_status),
                     smtp_status=COALESCE(excluded.smtp_status, emails.smtp_status),
                     disposable=COALESCE(excluded.disposable, emails.disposable),
                     catchall=COALESCE(excluded.catchall, emails.catchall),
                     verdict=COALESCE(excluded.verdict, emails.verdict),
                     verified_at=datetime('now')""",
                (company_id, e["email"], e["category"], e["source_url"],
                 e.get("mx_status"), e.get("smtp_status"), e.get("disposable"),
                 e.get("catchall"), e.get("verdict")),
            )
        for p in result.phones:
            conn.execute(
                """INSERT INTO phones(company_id, phone, label, source_url)
                   VALUES (?,?,?,?)
                   ON CONFLICT(company_id, phone) DO UPDATE SET
                     label=COALESCE(excluded.label, phones.label),
                     source_url=COALESCE(excluded.source_url, phones.source_url)""",
                (company_id, p["phone"], p.get("label"), p["source_url"]),
            )
        for s in result.socials:
            conn.execute(
                """INSERT INTO socials(company_id, network, url)
                   VALUES (?,?,?)
                   ON CONFLICT(company_id, network) DO UPDATE SET url=excluded.url""",
                (company_id, s["network"], s["url"]),
            )
        for person in result.people:
            li_url = person.get("linkedin_url")
            li_type = person.get("linkedin_type")
            if not li_url:
                # Fallback: a LinkedIn people-search deep link for the person
                # (honest — it is a search, not a confirmed profile).
                li_url = (
                    "https://www.linkedin.com/search/results/people/?keywords="
                    + quote(person["name"])
                )
                li_type = "search"
            # only save a person's email if it verified or the domain is catch-all
            email = person.get("email")
            email_status = person.get("email_status")
            if email and email_status in ("none-verified", "rejected", "invalid"):
                email, email_status = None, None
            conn.execute(
                """INSERT INTO people
                   (company_id, name, title, email, email_status, phone, phone_label,
                    linkedin_url, linkedin_type, mx_status, smtp_status, disposable,
                    catchall, verified_at, source_url)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),?)
                   ON CONFLICT(company_id, name) DO UPDATE SET
                     title=CASE WHEN excluded.title != '' THEN excluded.title ELSE people.title END,
                     email=COALESCE(excluded.email, people.email),
                     email_status=COALESCE(excluded.email_status, people.email_status),
                     phone=COALESCE(excluded.phone, people.phone),
                     phone_label=COALESCE(excluded.phone_label, people.phone_label),
                     linkedin_url=CASE WHEN excluded.linkedin_type='profile'
                                   THEN excluded.linkedin_url ELSE people.linkedin_url END,
                     linkedin_type=CASE WHEN excluded.linkedin_type='profile'
                                   THEN 'profile' ELSE people.linkedin_type END,
                     mx_status=COALESCE(excluded.mx_status, people.mx_status),
                     smtp_status=COALESCE(excluded.smtp_status, people.smtp_status),
                     disposable=COALESCE(excluded.disposable, people.disposable),
                     catchall=COALESCE(excluded.catchall, people.catchall),
                     verified_at=datetime('now'),
                     source_url=COALESCE(excluded.source_url, people.source_url)""",
                (company_id, person["name"], person.get("title"), email,
                 email_status, person.get("phone"), person.get("phone_label"),
                 li_url, li_type, person.get("mx_status"), person.get("smtp_status"),
                 person.get("disposable"), person.get("catchall"),
                 person["source_url"]),
            )
        conn.execute(
            """INSERT INTO scrapes(company_id, status, message, pages_checked, base_url, scraped_at)
               VALUES (?,?,?,?,?, datetime('now'))
               ON CONFLICT(company_id) DO UPDATE SET
                 status=excluded.status, message=excluded.message,
                 pages_checked=excluded.pages_checked, base_url=excluded.base_url,
                 scraped_at=excluded.scraped_at""",
            (company_id, result.status, result.message or "", result.pages_checked, result.base_url or ""),
        )
        conn.commit()
    finally:
        conn.close()


def scrape_company(company: dict[str, Any], force: bool = False) -> dict[str, Any]:
    company_id = company["id"]
    if not force:
        cached = cached_result(company_id)
        if cached["scraped"]:
            cached["cached"] = True
            return cached

    scraper, settings = scraper_config()
    result = scraper.scrape(company["domain"], company_name=company["name"])

    # If the organisation's own site publishes no decision makers, find them
    # from open sources (Wikipedia + open-web search — never LinkedIn scraping).
    find_web = settings.get("FIND_NAMES_WEB", DEFAULTS["FIND_NAMES_WEB"]).lower() != "false"
    if find_web and not result.people:
        try:
            from ..decision_finder import find_decision_makers

            found = find_decision_makers(company["name"], company["domain"])
            existing_names = {p["name"].lower() for p in result.people}
            for f in found:
                if f["name"].lower() not in existing_names:
                    result.people.append(f)
            if found:
                result.message = (
                    f"{result.message or ''} "
                    f"[+{len(found)} decision makers found via Wikipedia/open-web search]"
                ).strip()
        except Exception:
            pass

    # Verify emails BEFORE saving; keep only correct/verified data.
    _verify_and_finalize(result, settings)

    _store(company_id, result)

    out = cached_result(company_id)
    out["cached"] = False
    return out
