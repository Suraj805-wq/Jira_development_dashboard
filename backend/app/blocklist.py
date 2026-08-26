"""Organisation blocklist — keep unwanted companies out of the data warehouse.

- `DEFAULT_BLOCKED` holds the organisations the user asked to exclude.
- `normalize()` gives a canonical slug used for name matching.
- `apply_blocklist()` marks matching companies as blocked (idempotent).
- `is_blocked_domain()` / `is_blocked_name()` let lookup/discovery reject a
  company before it is ever added.
"""
from __future__ import annotations

import re

from .database import get_conn

# User-managed only. Industry leaders are part of the directory, not hidden.
DEFAULT_BLOCKED: list[tuple[str, str]] = []

# Names that used to be auto-blocked on every startup. Cleared once so Samsara,
# Geotab, Motive, Fleetx, etc. show up in the warehouse again.
_LEGACY_DEFAULT_NAMES = {
    "gurtam", "navixy", "geotab", "verizon connect", "samsara", "fleet complete",
    "fleetio", "gps wox", "gps server", "trackobit", "militrack", "protrack",
    "mapon", "watsoo", "gps trace", "onelap", "letstrack", "loconav", "wheelseye",
    "fleetx", "webfleet", "motive", "tomtom", "teletrac navman", "chevin fleet",
    "frotcom", "trimble", "quartix", "locus", "azuga",
}


def normalize(value: str) -> str:
    """Canonical slug for fuzzy name matching."""
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def ensure_default_blocklist() -> int:
    """Kept for compatibility — defaults are empty; exclusion is user-managed."""
    return 0


def clear_legacy_defaults() -> dict:
    """Remove the old competitor auto-blocklist and unhide those companies."""
    from .database import get_setting, set_setting

    if get_setting("legacy_blocklist_cleared") == "1":
        return {"cleared": 0, "already": True}
    conn = get_conn()
    removed = 0
    try:
        rows = conn.execute("SELECT id, name FROM blocklist").fetchall()
        for row in rows:
            if (row["name"] or "").strip().lower() in _LEGACY_DEFAULT_NAMES:
                conn.execute("DELETE FROM blocklist WHERE id = ?", (row["id"],))
                removed += 1
        conn.commit()
    finally:
        conn.close()
    apply_blocklist()
    set_setting("legacy_blocklist_cleared", "1")
    return {"cleared": removed, "already": False}


def _tokens(value: str) -> list[str]:
    """Word-level tokens, e.g. 'Teletrac Navman' -> ['teletrac','navman']."""
    return re.findall(r"[a-z0-9]+", (value or "").lower())


def _matches(company_name: str, company_domain: str, entry_name: str, entry_domain: str | None) -> bool:
    cn, en = normalize(company_name), normalize(entry_name)
    if not cn or not en:
        return False
    # 1) exact normalized equality
    if cn == en:
        return True
    # 2) word-token containment: every content token of the entry must appear
    #    as a whole token of the company name ("motive" in "Optimum Automotive"
    #    is NOT a token match, so it will not be blocked).
    entry_tokens = [t for t in _tokens(entry_name) if len(t) >= 2]
    company_tokens = _tokens(company_name)
    if entry_tokens and all(t in company_tokens for t in entry_tokens):
        return True
    # 3) single-token entry: also allow a company token to START with it
    #    (e.g. "onelap" matches "OnelapTelematics" written without spaces).
    if len(entry_tokens) == 1:
        e = entry_tokens[0]
        if len(e) >= 4 and any(c.startswith(e) for c in company_tokens):
            return True
    # 4) domain match
    if entry_domain:
        d = normalize(entry_domain)
        cd = normalize(company_domain or "")
        if d and (cd == d or cd.endswith("." + d) or d.endswith("." + cd)):
            return True
    return False


def apply_blocklist() -> dict:
    """Full recompute: mark matching companies blocked=1, unmark the rest.

    Idempotent and self-correcting — safe to call at every startup and after
    any blocklist change.
    """
    conn = get_conn()
    marked: list[str] = []
    unmarked: list[str] = []
    try:
        entries = conn.execute("SELECT name, domain FROM blocklist").fetchall()
        companies = conn.execute("SELECT id, name, domain, blocked FROM companies").fetchall()
        for comp in companies:
            should_block = any(
                _matches(comp["name"], comp["domain"], entry["name"], entry["domain"])
                for entry in entries
            )
            if should_block and not comp["blocked"]:
                conn.execute("UPDATE companies SET blocked = 1 WHERE id = ?", (comp["id"],))
                marked.append(comp["name"])
            elif not should_block and comp["blocked"]:
                conn.execute("UPDATE companies SET blocked = 0 WHERE id = ?", (comp["id"],))
                unmarked.append(comp["name"])
        conn.commit()
    finally:
        conn.close()
    return {"marked_blocked": marked, "unmarked": unmarked, "count": len(marked)}


def is_blocked_candidate(name: str, domain: str | None) -> bool:
    """True if a company about to be added (lookup/discover) matches the blocklist."""
    conn = get_conn()
    try:
        entries = conn.execute("SELECT name, domain FROM blocklist").fetchall()
    finally:
        conn.close()
    for entry in entries:
        if _matches(name, domain or "", entry["name"], entry["domain"]):
            return True
        # also block if the domain itself is on the blocklist
        if domain and entry["domain"] and normalize(domain) == normalize(entry["domain"]):
            return True
    return False


def blocklist_status() -> list[dict]:
    """Return blocklist entries with the companies they currently block."""
    conn = get_conn()
    try:
        entries = conn.execute("SELECT id, name, domain FROM blocklist ORDER BY name").fetchall()
        out = []
        for e in entries:
            blocked = conn.execute(
                "SELECT id, name, domain FROM companies WHERE blocked = 1"
            ).fetchall()
            matching = [
                {"id": b["id"], "name": b["name"], "domain": b["domain"]}
                for b in blocked
                if _matches(b["name"], b["domain"], e["name"], e["domain"])
            ]
            out.append({
                "id": e["id"],
                "name": e["name"],
                "domain": e["domain"],
                "blocks_companies": matching,
            })
        return out
    finally:
        conn.close()


def add_blocklist(name: str, domain: str | None) -> dict:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO blocklist(name, domain) VALUES (?, ?)",
            (name.strip(), (domain or "").strip() or None),
        )
        conn.commit()
        inserted = cur.rowcount > 0
    finally:
        conn.close()
    if inserted:
        apply_blocklist()
    return {"added": inserted, "name": name}


def remove_blocklist(entry_id: int) -> dict:
    """Remove a blocklist entry and unblock companies it alone matched."""
    conn = get_conn()
    try:
        entry = conn.execute("SELECT * FROM blocklist WHERE id = ?", (entry_id,)).fetchone()
        if not entry:
            return {"removed": False}
        conn.execute("DELETE FROM blocklist WHERE id = ?", (entry_id,))
        conn.commit()
        # unblock companies that no longer match ANY remaining entry
        remaining = conn.execute("SELECT name, domain FROM blocklist").fetchall()
        blocked = conn.execute("SELECT id, name, domain FROM companies WHERE blocked = 1").fetchall()
        unblocked = []
        for comp in blocked:
            still = any(
                _matches(comp["name"], comp["domain"], r["name"], r["domain"])
                for r in remaining
            )
            if not still:
                conn.execute("UPDATE companies SET blocked = 0 WHERE id = ?", (comp["id"],))
                unblocked.append(comp["name"])
        conn.commit()
    finally:
        conn.close()
    return {"removed": True, "unblocked": unblocked}
