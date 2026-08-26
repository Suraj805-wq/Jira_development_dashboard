"""Email verification endpoints (open-source MX + SMTP checks)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..database import get_conn
from ..enrichment.verify import verify_and_stamp, verify_email

router = APIRouter(prefix="/api", tags=["verify"])


@router.get("/verify")
def verify_single(email: str = Query(...)):
    """Verify one address on demand (not persisted)."""
    return verify_email(email)


@router.post("/companies/{company_id}/verify")
def verify_company(company_id: int):
    """Verify every stored email (company + executives) and persist results."""
    conn = get_conn()
    try:
        comp = conn.execute("SELECT id FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not comp:
            raise HTTPException(status_code=404, detail="Company not found")

        addresses: dict[str, str] = {}  # email -> table
        for r in conn.execute("SELECT email FROM emails WHERE company_id = ?", (company_id,)):
            if r["email"]:
                addresses[r["email"]] = "emails"
        for r in conn.execute("SELECT email FROM people WHERE company_id = ? AND email IS NOT NULL", (company_id,)):
            if r["email"]:
                addresses[r["email"]] = "people"
    finally:
        conn.close()

    summary = {"total": 0, "deliverable": 0, "risky": 0, "disposable": 0, "mx_ok": 0, "unknown": 0, "invalid": 0}
    conn = get_conn()
    try:
        for email, table in addresses.items():
            res = verify_and_stamp(email)
            summary["total"] += 1
            summary[res["verdict"]] = summary.get(res["verdict"], 0) + 1
            if table == "emails":
                conn.execute(
                    "UPDATE emails SET mx_status=?, smtp_status=?, disposable=?, verified_at=? WHERE company_id=? AND email=?",
                    (res["mx_status"], res["smtp_status"], res["disposable"], res["verified_at"], company_id, email),
                )
            else:
                conn.execute(
                    "UPDATE people SET mx_status=?, smtp_status=?, disposable=?, verified_at=? WHERE company_id=? AND email=?",
                    (res["mx_status"], res["smtp_status"], res["disposable"], res["verified_at"], company_id, email),
                )
        conn.commit()
    finally:
        conn.close()
    return summary


@router.post("/verify/all")
def verify_all(limit: int = Query(50, ge=1, le=300)):
    """Bulk-verify across the whole directory (persists results)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, email FROM emails WHERE smtp_status IS NULL
               UNION ALL
               SELECT id, email FROM people WHERE email IS NOT NULL AND smtp_status IS NULL
               LIMIT ?""", (limit,),
        ).fetchall()
    finally:
        conn.close()

    summary = {"total": 0, "deliverable": 0, "risky": 0, "disposable": 0, "mx_ok": 0, "unknown": 0, "invalid": 0}
    conn = get_conn()
    try:
        for r in rows:
            email = r["email"]
            if not email:
                continue
            res = verify_and_stamp(email)
            summary["total"] += 1
            summary[res["verdict"]] = summary.get(res["verdict"], 0) + 1
            # Try both tables (id spaces overlap, so update by email+table where possible)
            conn.execute(
                "UPDATE emails SET mx_status=?, smtp_status=?, disposable=?, verified_at=? WHERE email=?",
                (res["mx_status"], res["smtp_status"], res["disposable"], res["verified_at"], email),
            )
            conn.execute(
                "UPDATE people SET mx_status=?, smtp_status=?, disposable=?, verified_at=? WHERE email=?",
                (res["mx_status"], res["smtp_status"], res["disposable"], res["verified_at"], email),
            )
        conn.commit()
    finally:
        conn.close()
    return summary
