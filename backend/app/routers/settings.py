"""Scraper + verification behaviour settings (all local, open-source)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..database import all_settings, set_setting

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ScraperSettingsIn(BaseModel):
    respect_robots: bool = True
    request_delay: float = 1.0
    max_pages: int = 10
    derive_emails: bool = True
    verify_on_save: bool = True
    smtp_timeout: int = 8
    max_email_candidates: int = 11
    find_names_web: bool = True
    proxy_url: str | None = None


def _current() -> dict:
    s = all_settings()
    return {
        "respect_robots": s.get("RESPECT_ROBOTS", "true").lower() != "false",
        "request_delay": float(s.get("REQUEST_DELAY", "1.0")),
        "max_pages": int(s.get("MAX_PAGES", "10")),
        "derive_emails": s.get("DERIVE_EMAILS", "true").lower() != "false",
        "verify_on_save": s.get("VERIFY_ON_SAVE", "true").lower() != "false",
        "smtp_timeout": int(s.get("SMTP_TIMEOUT", "8")),
        "max_email_candidates": int(s.get("MAX_EMAIL_CANDIDATES", "11")),
        "find_names_web": s.get("FIND_NAMES_WEB", "true").lower() != "false",
        "proxy_url": s.get("PROXY_URL") or "",
    }


@router.get("")
def get_settings():
    return _current()


@router.put("")
def update_settings(body: ScraperSettingsIn):
    set_setting("RESPECT_ROBOTS", "true" if body.respect_robots else "false")
    set_setting("REQUEST_DELAY", str(max(0.0, min(10.0, body.request_delay))))
    set_setting("MAX_PAGES", str(max(1, min(15, body.max_pages))))
    set_setting("DERIVE_EMAILS", "true" if body.derive_emails else "false")
    set_setting("VERIFY_ON_SAVE", "true" if body.verify_on_save else "false")
    set_setting("SMTP_TIMEOUT", str(max(2, min(30, body.smtp_timeout))))
    set_setting("MAX_EMAIL_CANDIDATES", str(max(1, min(20, body.max_email_candidates))))
    set_setting("FIND_NAMES_WEB", "true" if body.find_names_web else "false")
    if body.proxy_url is not None:
        set_setting("PROXY_URL", body.proxy_url.strip())
    return _current()
