"""Open-source email verification.

Checks performed (in order of confidence):

1. **Syntax**       — RFC-ish shape.
2. **Disposable**   — known throwaway domains (mailinator, etc.).
3. **MX**           — does the domain publish mail servers? (dnspython)
4. **Catch-all**    — is the domain a catch-all (accepts mail for ANY address)?
   If so, SMTP answers can't prove a mailbox exists, so results are downgraded
   to "catchall" instead of "deliverable".
5. **SMTP handshake** — connect to the MX, EHLO, MAIL FROM, RCPT TO and read the
   server's response. 250/251/252 => "deliverable"; 550/5xx => "rejected".

Also provides `generate_candidates()` (all common naming conventions for a
person's name) and `verify_candidates()` (verify each until one is deliverable)
so a decision maker's email can be found by trying combinations — the same
technique every free/paid verifier uses.

Dependencies: dnspython (ISC-style open-source license) + stdlib smtplib.
"""
from __future__ import annotations

import random
import re
import smtplib
import socket
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import dns.resolver

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

DISPOSABLE_DOMAINS = {
    "mailinator.com", "yopmail.com", "tempmail.com", "temp-mail.org",
    "guerrillamail.com", "sharklasers.com", "grr.la", "10minutemail.com",
    "throwawaymail.com", "mailnesia.com", "trashmail.com", "getnada.com",
    "dispostable.com", "fakeinbox.com", "mintemail.com", "maildrop.cc",
    "harakirimail.com", "spamgourmet.com", "tempr.email", "dropmail.me",
    "emailondeck.com", "mohmal.com", "tmpmail.org", "temporary-mail.net",
    "0wnd.net", "0wnd.org", "spam4.me", "wegwerfmail.de", "wegwerfmail.net",
    "jetable.org", "emailfake.com", "burnermail.io", "mailsac.com",
}

FROM_EMAIL = "verify@fleetleads.local"
CATCHALL_LOCAL = "fleetleads-catchall-test-{}".format(random.randint(100000, 999999))

_mx_cache: dict[str, list[str]] = {}
_catchall_cache: dict[str, str] = {}


def _ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def generate_candidates(full_name: str, domain: str) -> list[str]:
    """Generate common email combinations for a person's name at a domain."""
    tokens = [t for t in re.split(r"[^A-Za-zÀ-ÖØ-öø-ÿ\u0100-\u017f\u0180-\u024f]+", (full_name or "").strip()) if t]
    tokens = [t for t in tokens if len(t) >= 2]
    if len(tokens) < 2:
        return []
    first = _ascii(tokens[0]).lower()
    last = _ascii(tokens[-1]).lower()
    fi = first[0]
    li = last[0]
    locals = [
        f"{first}.{last}",       # first.last
        f"{first}{li}",          # firstl
        f"{fi}{last}",           # flast
        f"{fi}.{last}",          # f.last
        f"{first}_{last}",       # first_last
        f"{first}-{last}",       # first-last
        f"{first}",              # first
        f"{fi}{li}",             # fl
        f"{last}.{first}",       # last.first
        f"{first}.{li}",         # first.l
        f"{fi}.{li}",            # f.l
    ]
    seen: set[str] = set()
    out: list[str] = []
    for loc in locals:
        if loc not in seen:
            seen.add(loc)
            out.append(f"{loc}@{domain}")
    return out


def _syntax(email: str) -> bool:
    return bool(EMAIL_RE.match(email)) and email.count("@") == 1


def _is_disposable(email: str) -> bool:
    return email.split("@")[-1].lower() in DISPOSABLE_DOMAINS


def _mx_hosts(domain: str) -> list[str]:
    domain = domain.lower()
    if domain in _mx_cache:
        return _mx_cache[domain]
    try:
        answers = dns.resolver.resolve(domain, "MX")
        hosts = [str(a.exchange).rstrip(".") for a in sorted(answers, key=lambda a: a.preference)]
    except Exception:
        hosts = []
    _mx_cache[domain] = hosts
    return hosts


def _smtp_rcpt(mx_hosts: list[str], address: str, timeout: int = 8) -> str:
    """Return 'deliverable' | 'rejected' | 'blocked' | 'unknown' for one RCPT."""
    if not mx_hosts:
        return "unknown"
    last = "unknown"
    for host in mx_hosts[:3]:
        try:
            with smtplib.SMTP(host, 25, timeout=timeout) as s:
                s.ehlo("fleetleads.local")
                code, _ = s.mail(FROM_EMAIL)
                if code >= 400:
                    return "blocked"
                code, _ = s.rcpt(address)
                if code in (250, 251, 252):
                    return "deliverable"
                if 500 <= code <= 599:
                    return "rejected"
                last = "unknown"
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError):
            continue
        except socket.timeout:
            last = "unknown"
            continue
        except OSError:
            return "blocked"
        except Exception:
            continue
    return last


def detect_catchall(domain: str, timeout: int = 8) -> str:
    """Detect whether a domain is a catch-all mailbox.

    Returns 'yes' | 'no' | 'unknown'. A catch-all domain accepts mail for every
    address, so an SMTP 'deliverable' there cannot prove a mailbox exists.
    """
    domain = domain.lower()
    if domain in _catchall_cache:
        return _catchall_cache[domain]
    mx = _mx_hosts(domain)
    if not mx:
        _catchall_cache[domain] = "unknown"
        return "unknown"
    test_addr = f"{CATCHALL_LOCAL}@{domain}"
    result = _smtp_rcpt(mx, test_addr, timeout)
    verdict = "yes" if result == "deliverable" else ("no" if result == "rejected" else "unknown")
    _catchall_cache[domain] = verdict
    return verdict


def verify_email(email: str, timeout: int = 8, use_cache: bool = True) -> dict:
    """Verify one address; returns a dict with statuses and a verdict."""
    email = (email or "").strip().lower()
    result = {
        "email": email,
        "syntax": _syntax(email),
        "disposable": _is_disposable(email),
        "mx_status": None,
        "smtp_status": None,
        "catchall": None,
        "verdict": "invalid",
        "detail": "",
    }
    if not result["syntax"]:
        result["verdict"] = "invalid"
        result["detail"] = "Malformed address."
        return result
    if result["disposable"]:
        result["verdict"] = "disposable"
        result["detail"] = "Disposable / throwaway mailbox."
        return result

    domain = email.split("@")[-1]
    mx = _mx_hosts(domain)
    if not mx:
        result["verdict"] = "invalid"
        result["mx_status"] = "missing"
        result["detail"] = "Domain has no MX records — cannot receive mail."
        return result
    result["mx_status"] = "ok"

    smtp = _smtp_rcpt(mx, email, timeout)
    result["smtp_status"] = smtp

    if smtp == "deliverable":
        catchall = detect_catchall(domain, timeout)
        result["catchall"] = catchall
        if catchall == "yes":
            result["verdict"] = "catchall"
            result["detail"] = "Mail server accepts all addresses (catch-all) — cannot confirm this mailbox specifically."
        else:
            result["verdict"] = "deliverable"
            result["detail"] = "Mailbox accepted by the mail server."
    elif smtp == "rejected":
        result["verdict"] = "rejected"
        result["detail"] = "Mail server rejected this address (likely nonexistent)."
    elif smtp == "blocked":
        result["verdict"] = "blocked"
        result["detail"] = "Outbound SMTP blocked from this host — MX is valid but mailbox unconfirmed."
    else:
        result["verdict"] = "mx-ok"
        result["detail"] = "Domain accepts mail (MX valid); mailbox not confirmed."
    return result


def verify_candidates(emails: list[str], timeout: int = 8) -> dict:
    """Verify a list of candidate emails; stop at the first confirmed deliverable.

    Returns:
      {"winner": email_or_None, "winner_verdict": ..., "results": {email: verdict}}
    """
    # quick pre-filter: syntax + disposable + MX
    results: dict[str, str] = {}
    candidates = []
    for e in emails:
        r = verify_email(e, timeout=timeout)
        results[e] = r["verdict"]
        if r["verdict"] == "deliverable":
            return {"winner": e, "winner_verdict": "deliverable", "results": results}
        if r["verdict"] == "catchall":
            candidates.append((e, "catchall"))
        elif r["verdict"] in ("mx-ok", "blocked", "unknown"):
            candidates.append((e, r["verdict"]))
    # no deliverable found; prefer a catchall, then an mx-ok
    for e, v in candidates:
        if v == "catchall":
            return {"winner": e, "winner_verdict": "catchall", "results": results}
    for e, v in candidates:
        if v == "mx-ok":
            return {"winner": e, "winner_verdict": "mx-ok", "results": results}
    return {"winner": None, "winner_verdict": None, "results": results}


def verify_many(emails: list[str], max_workers: int = 4, timeout: int = 8) -> dict[str, str]:
    """Verify many independent addresses concurrently. Returns {email: verdict}."""
    out: dict[str, str] = {}
    if not emails:
        return out
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(verify_email, e, timeout): e for e in emails}
        for fut in as_completed(futures):
            e = futures[fut]
            try:
                out[e] = fut.result()["verdict"]
            except Exception:
                out[e] = "unknown"
    return out


def verify_and_stamp(email: str) -> dict:
    """Verify and return the column values to persist."""
    r = verify_email(email)
    return {
        "mx_status": r["mx_status"],
        "smtp_status": r["smtp_status"],
        "disposable": "yes" if r["disposable"] else "no",
        "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **r,
    }
