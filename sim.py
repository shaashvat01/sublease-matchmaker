"""Run the matchmaking and an agent-to-agent negotiation in the terminal, without Discord.

    .venv/bin/python sim.py            # uses Claude on Bedrock
"""

import json
from pathlib import Path

from app import matching, referee
from app.models import Leaver, Seeker
from app.negotiation import negotiate

data = json.loads(Path("data/listings.json").read_text())
leavers = [Leaver(**l) for l in data["leavers"]]
seeker = Seeker(**data["seekers"][0])

ranked = matching.rank(leavers, seeker)
print("Matches for", seeker.name)
for m in ranked:
    print(" ", m)
best = next(l for l in leavers if l.id == ranked[0]["leaver_id"])
card = matching.make_card(best, verified=True)
print("\nNegotiating over:", card.model_dump_json())


def show(t):
    o = t.offer
    terms = f" | {o.move_in}→{o.move_out} ${o.monthly_rent}/mo dep ${o.deposit}" if o else ""
    print(f"[{t.round:>2}] {t.side:<7} {t.action:<8}{terms}\n      {t.message}" + (f"\n      flags: {t.flags}" if t.flags else ""))


deal, turns = negotiate(best, seeker, card, on_turn=show)
print("\nDEAL:" if deal else "\nNO DEAL", deal.model_dump_json() if deal else "")
if deal:
    print("Stay total:", referee.stay_total(deal))
    assert referee.can_accept("leaver", deal, best) and referee.can_accept("seeker", deal, seeker)
