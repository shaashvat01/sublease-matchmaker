"""The referee: plain-code rules that sit between the two agents.

The language models negotiate; this file makes sure no offer crosses its own student's private limits, no private
number leaks into a message, and no listing text expresses a preference the Fair Housing Act forbids.
"""

from __future__ import annotations

import re
from datetime import timedelta

from .models import Leaver, Offer, Seeker

MAX_ROUNDS = 6

# Words that signal a preference on a protected characteristic (42 U.S.C. 3604(c)). Lifestyle rules such as
# "no smoking" or "quiet after 10" are fine and are not on this list.
PROTECTED = re.compile(
    r"\b(male|female|men|women|guys?|girls?|gay|straight|christian|muslim|jewish|hindu|church|"
    r"no kids|no children|couples? only|singles? only|white|black|asian|hispanic|latino|indian|"
    r"american only|english only|disabled|wheelchair|pregnan\w*)\b",
    re.I,
)


def leaver_window(me: Leaver) -> tuple:
    flex = timedelta(days=me.flex_days)
    return me.available_from - flex, me.available_to + flex


def check_offer(side: str, offer: Offer, me) -> tuple[Offer, list[str]]:
    """Clamp an outgoing offer to the sender's own limits. Returns the safe offer and what was changed."""
    flags = []
    o = offer.model_copy()
    if side == "leaver":
        if o.monthly_rent < me.floor_rent:
            o.monthly_rent, flags = me.floor_rent, flags + ["raised rent to the leaver's floor"]
        earliest, latest = leaver_window(me)
        if o.move_in < earliest:
            o.move_in, flags = earliest, flags + ["moved move-in into the leaver's window"]
        if o.move_out > latest:
            o.move_out, flags = latest, flags + ["moved move-out into the leaver's window"]
    else:
        if o.monthly_rent > me.max_rent:
            o.monthly_rent, flags = me.max_rent, flags + ["capped rent at the seeker's max"]
    if o.move_out <= o.move_in:
        o.move_out, flags = o.move_in + timedelta(days=30), flags + ["fixed move-out before move-in"]
    return o, flags


def can_accept(side: str, offer: Offer, me) -> bool:
    """An agent may only accept an offer that is inside its own student's limits."""
    if side == "leaver":
        earliest, latest = leaver_window(me)
        return offer.monthly_rent >= me.floor_rent and offer.move_in >= earliest and offer.move_out <= latest
    flex = timedelta(days=me.flex_days)
    covers = offer.move_in <= me.need_from + flex and offer.move_out >= me.need_to - flex
    return offer.monthly_rent <= me.max_rent and covers


def secrets_of(side: str, me) -> list[int]:
    return [me.floor_rent] if side == "leaver" else [me.max_rent]


def scrub(text: str, secrets: list[int], public: tuple = ()) -> tuple[str, list[str]]:
    """Redact any private number and any protected-class wording from text the other side will read.

    A number that is already public (it's the rent in an offer on the table) is left alone.
    """
    flags = []
    for n in secrets:
        if n in public:
            continue
        pattern = rf"\$?\b{n:,}\b|\$?\b{n}\b".replace(",", ",?")
        if re.search(pattern, text):
            text, flags = re.sub(pattern, "[private]", text), flags + ["redacted a private number"]
    if PROTECTED.search(text):
        text, flags = PROTECTED.sub("[removed]", text), flags + ["removed protected-class wording"]
    return text, flags


def zone_of_agreement(leaver: Leaver, seeker: Seeker) -> tuple[int, int] | None:
    """The rent range both could accept, known only to the referee."""
    lo, hi = leaver.floor_rent, seeker.max_rent
    return (lo, hi) if lo <= hi else None


def midpoint(leaver_ask: int, seeker_bid: int, leaver: Leaver, seeker: Seeker) -> int | None:
    """Split the difference between the two last *public* offers, if both students could live with it.

    Using the public offers (not the private limits) means the suggestion reveals nothing either side
    couldn't already see.
    """
    zone = zone_of_agreement(leaver, seeker)
    if not zone:
        return None
    mid = int(round((leaver_ask + seeker_bid) / 2 / 5) * 5)
    return mid if zone[0] <= mid <= zone[1] else None


def stay_total(offer: Offer) -> int:
    """Total rent for the stay, prorated by day (a 30-day month)."""
    days = (offer.move_out - offer.move_in).days
    return int(round(offer.monthly_rent * days / 30))
