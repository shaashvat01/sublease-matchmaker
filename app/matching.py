"""Match seekers to listings: date overlap, budget fit and commute time to the seeker's office."""

from __future__ import annotations

import math
from datetime import date

from .models import Card, Leaver, Seeker
from .referee import PROTECTED


def make_card(leaver: Leaver, verified: bool = False) -> Card:
    """The public card. Rules with protected-class wording never reach the board."""
    rules = [r for r in leaver.house_rules if not PROTECTED.search(r)]
    return Card(
        leaver_id=leaver.id,
        neighborhood=leaver.neighborhood,
        available=f"{leaver.available_from:%b %d} – {leaver.available_to:%b %d}",
        rent=leaver.asking_rent,
        room_type=leaver.room_type,
        furnished=leaver.furnished,
        utilities_included=leaver.utilities_included,
        house_rules=rules,
        verified=verified,
    )


def overlap_days(a_from: date, a_to: date, b_from: date, b_to: date) -> int:
    return max(0, (min(a_to, b_to) - max(a_from, b_from)).days)


def commute(leaver: Leaver, seeker: Seeker) -> int:
    """Door-to-door minutes from the listing to the office (about 18 km/h, plus a 5-minute walk)."""
    km = haversine_km(leaver.lat, leaver.lng, seeker.office_lat, seeker.office_lng)
    return round(km / 18 * 60) + 5


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def score(leaver: Leaver, seeker: Seeker) -> dict | None:
    """How well a listing fits a seeker, using only public listing data plus the seeker's own needs."""
    need = (seeker.need_to - seeker.need_from).days or 1
    days = overlap_days(leaver.available_from, leaver.available_to, seeker.need_from, seeker.need_to)
    coverage = days / need
    if coverage < 0.5:
        return None
    if leaver.asking_rent > seeker.max_rent * 1.25:
        return None  # too far apart to be worth negotiating
    minutes = commute(leaver, seeker)
    budget = min(1.0, seeker.max_rent / leaver.asking_rent)
    points = 50 * coverage + 30 * budget + 20 * max(0.0, 1 - minutes / 60)
    return {"leaver_id": leaver.id, "score": round(points), "coverage": round(coverage, 2),
            "commute_min": minutes}


def rank(listings: list[Leaver], seeker: Seeker) -> list[dict]:
    found = [s for s in (score(l, seeker) for l in listings) if s]
    return sorted(found, key=lambda s: s["score"], reverse=True)
