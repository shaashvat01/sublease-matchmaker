"""SQLite storage: one profile per Discord user, and the negotiations between them."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Optional

from .models import Leaver, Offer, Seeker

DB = Path(__file__).resolve().parent.parent / "data" / "sublease.db"


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, discord_id INTEGER, role TEXT, data TEXT, verified INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS negotiations (id TEXT PRIMARY KEY, leaver_id TEXT, seeker_id TEXT, status TEXT,
            deal TEXT, leaver_ok INTEGER DEFAULT 0, seeker_ok INTEGER DEFAULT 0, thread_id INTEGER);
    """)
    return conn


def save_profile(p: Leaver | Seeker, verified: bool = False) -> None:
    role = "leaver" if isinstance(p, Leaver) else "seeker"
    with db() as c:
        c.execute("INSERT OR REPLACE INTO profiles VALUES (?,?,?,?,?)", (p.id, p.discord_id, role, p.model_dump_json(), int(verified)))


def replace_profiles_of(discord_id: int) -> None:
    """A student has one profile: drop the old one before saving a new one."""
    with db() as c:
        c.execute("DELETE FROM profiles WHERE discord_id=?", (discord_id,))


def profile(pid: str) -> Optional[Leaver | Seeker]:
    row = db().execute("SELECT role, data FROM profiles WHERE id=?", (pid,)).fetchone()
    if not row:
        return None
    return (Leaver if row["role"] == "leaver" else Seeker).model_validate_json(row["data"])


def profile_of(discord_id: int) -> Optional[Leaver | Seeker]:
    row = db().execute("SELECT id FROM profiles WHERE discord_id=?", (discord_id,)).fetchone()
    return profile(row["id"]) if row else None


def is_verified(pid: str) -> bool:
    row = db().execute("SELECT verified FROM profiles WHERE id=?", (pid,)).fetchone()
    return bool(row and row["verified"])


def leavers(guild_id: Optional[int] = None) -> list[Leaver]:
    """Listings visible in one server: its own, plus the shared starter listings (no server)."""
    rows = db().execute("SELECT data FROM profiles WHERE role='leaver'").fetchall()
    found = [Leaver.model_validate_json(r["data"]) for r in rows]
    return [l for l in found if l.guild_id in (None, guild_id)]


def new_negotiation(leaver_id: str, seeker_id: str) -> str:
    nid = uuid.uuid4().hex[:8]
    with db() as c:
        c.execute("INSERT INTO negotiations (id, leaver_id, seeker_id, status) VALUES (?,?,?,?)", (nid, leaver_id, seeker_id, "pending"))
    return nid


def negotiation(nid: str) -> Optional[sqlite3.Row]:
    return db().execute("SELECT * FROM negotiations WHERE id=?", (nid,)).fetchone()


def update_negotiation(nid: str, **fields) -> None:
    if "deal" in fields and isinstance(fields["deal"], Offer):
        fields["deal"] = fields["deal"].model_dump_json()
    sets = ", ".join(f"{k}=?" for k in fields)
    with db() as c:
        c.execute(f"UPDATE negotiations SET {sets} WHERE id=?", (*fields.values(), nid))


def deal_of(row: sqlite3.Row) -> Optional[Offer]:
    return Offer.model_validate_json(row["deal"]) if row["deal"] else None


def new_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:6]}"


def seed(path: Path) -> int:
    """Load the starting listings."""
    data = json.loads(path.read_text())
    for raw in data["leavers"]:
        save_profile(Leaver(**raw), verified=True)
    return len(data["leavers"])
