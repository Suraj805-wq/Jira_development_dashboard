"""Blocklist management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import blocklist
from ..database import get_conn

router = APIRouter(prefix="/api", tags=["blocklist"])


class BlocklistAdd(BaseModel):
    name: str
    domain: str | None = None


@router.get("/blocklist")
def get_blocklist():
    return {"entries": blocklist.blocklist_status()}


@router.post("/blocklist")
def add_to_blocklist(body: BlocklistAdd):
    return blocklist.add_blocklist(body.name, body.domain)


@router.delete("/blocklist/{entry_id}")
def delete_blocklist(entry_id: int):
    return blocklist.remove_blocklist(entry_id)


@router.post("/blocklist/apply")
def reapply_blocklist():
    return blocklist.apply_blocklist()


@router.post("/companies/{company_id}/block")
def block_company(company_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT id, name, domain FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Company not found")
        conn.execute("UPDATE companies SET blocked = 1 WHERE id = ?", (company_id,))
        conn.execute(
            "INSERT OR IGNORE INTO blocklist(name, domain) VALUES (?, ?)",
            (row["name"], row["domain"]),
        )
        conn.commit()
        return {"blocked": True, "name": row["name"]}
    finally:
        conn.close()


@router.post("/companies/{company_id}/unblock")
def unblock_company(company_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT id, name FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Company not found")
        conn.execute("UPDATE companies SET blocked = 0 WHERE id = ?", (company_id,))
        conn.commit()
        return {"blocked": False, "name": row["name"]}
    finally:
        conn.close()
