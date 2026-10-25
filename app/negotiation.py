"""Two personal agents negotiate a sublease, turn by turn, through the referee."""

from __future__ import annotations

import os
from typing import Callable, Optional

from strands import Agent
from strands.models import BedrockModel

from . import referee
from .models import Card, Leaver, Move, Offer, Seeker, Turn
from .referee_agent import RefereeAgent

MODEL_ID = os.environ.get("NEGOTIATOR_MODEL", "us.anthropic.claude-sonnet-5-5")
REGION = os.environ.get("BEDROCK_REGION", "us-east-1")

COMMON = """You negotiate a summer sublease by trading short structured moves with another student's agent.
Rules:
- You represent only your own student. Never reveal their private limits (the numbers marked PRIVATE), not even hints like "my max is close to".
- Keep each message to one or two friendly sentences. No pressure tactics.
- Prorate when the dates only partly overlap, and suggest small date changes when they help both sides.
- Never mention or ask about race, religion, national origin, sex, disability or family status.
- Accept when the offer on the table is good for your student and inside their limits; don't drag it out.
- Use "reject" only when no deal inside your limits is possible."""


def leaver_prompt(me: Leaver) -> str:
    return f"""{COMMON}

You are the agent for {me.name}, who is subleasing their {me.room_type} in {me.neighborhood}.
Listing: available {me.available_from} to {me.available_to}, asking ${me.asking_rent}/month,
deposit ${me.deposit}, utilities {"included" if me.utilities_included else "not included"},
{"furnished" if me.furnished else "unfurnished"}. House rules: {", ".join(me.house_rules) or "none"}.
{"Roommates must approve the subtenant before anything is final." if me.roommate_approval else ""}
PRIVATE: the lowest monthly rent {me.name} will accept is ${me.floor_rent}. Dates can move by up to {me.flex_days} days.
Goal: fill the room for as much of the window as possible at a fair price at or above the floor."""


def seeker_prompt(me: Seeker) -> str:
    return f"""{COMMON}

You are the agent for {me.name}, who needs a place near {me.office_name} from {me.need_from} to {me.need_to}.
They would like to pay about ${me.target_rent}/month.
Must-haves: {", ".join(me.must_haves) or "none"}. Deal-breakers: {", ".join(me.deal_breakers) or "none"}.
PRIVATE: the most {me.name} can pay is ${me.max_rent}/month. Dates can move by up to {me.flex_days} days.
Goal: cover the internship dates at the lowest fair price."""


class Negotiator:
    def __init__(self, side: str, profile, model_id: str = MODEL_ID):
        self.side, self.me = side, profile
        prompt = leaver_prompt(profile) if side == "leaver" else seeker_prompt(profile)
        model = BedrockModel(model_id=model_id, region_name=REGION, max_tokens=4000)
        self.agent = Agent(model=model, system_prompt=prompt, callback_handler=None, name=f"{side}-agent")

    def move(self, situation: str) -> Move:
        return self.agent(situation, structured_output_model=Move).structured_output


def describe(offer: Optional[Offer]) -> str:
    if not offer:
        return "No offer on the table yet."
    return (f"Offer on the table: move in {offer.move_in}, move out {offer.move_out}, ${offer.monthly_rent}/month "
            f"(about ${referee.stay_total(offer)} for the stay), deposit ${offer.deposit}, utilities "
            f"{'included' if offer.utilities_included else 'not included'}. Notes: {offer.notes or 'none'}")


def negotiate(leaver: Leaver, seeker: Seeker, card: Card, on_turn: Callable[[Turn], None] = lambda t: None,
              model_id: str = MODEL_ID) -> tuple[Optional[Offer], list[Turn]]:
    """Run the negotiation. Returns the agreed offer (or None) and every turn, as checked by the referee."""
    agents = {"leaver": Negotiator("leaver", leaver, model_id), "seeker": Negotiator("seeker", seeker, model_id)}
    judge = RefereeAgent(leaver, seeker)
    turns: list[Turn] = []
    on_table: Optional[Offer] = None
    last_rent = {"leaver": card.rent, "seeker": None}

    def log(t: Turn):
        turns.append(t)
        on_turn(t)

    def clean(side, message, offer, stuck=False, full=False):
        """Hard rules first (private numbers, protected wording), then the Sonnet referee's review."""
        public = (offer.monthly_rent,) if offer else ()
        text, flags = referee.scrub(message, referee.secrets_of(side, agents[side].me), public)
        last = f"leaver asked ${last_rent['leaver']}, seeker offered ${last_rent['seeker']}"
        verdict = judge.review(side, text, offer, stuck=stuck, last_offers=last)
        flags += [f"referee: {i}" for i in verdict.issues]
        return (verdict.message, flags, verdict) if full else (verdict.message, flags)

    side = "seeker"
    situation = (f"You found this listing: {card.model_dump_json()}. Its commute and dates fit your student. "
                 f"Open the negotiation with a first offer.")
    for rnd in range(1, referee.MAX_ROUNDS * 2 + 1):
        me = agents[side].me
        mv = agents[side].move(situation)
        flags: list[str] = []

        if mv.action == "accept":
            if on_table and referee.can_accept(side, on_table, me):
                text, more = clean(side, mv.message, on_table)
                log(Turn(round=rnd, side=side, action="accept", offer=on_table, message=text, flags=more))
                return on_table, turns
            # Hard rule: an agent can't accept outside its student's limits. Retry once as a counter.
            flags.append("accept blocked: outside this student's limits")
            mv = agents[side].move("The referee blocked that accept: it is outside your student's limits. Counter instead.")

        if mv.action == "reject" or not mv.offer:
            text, more = clean(side, mv.message, None)
            log(Turn(round=rnd, side=side, action="reject", message=text, flags=flags + more))
            return None, turns

        offer, fixes = referee.check_offer(side, mv.offer, me)
        offer.notes, _ = referee.scrub(offer.notes, referee.secrets_of(side, me), (offer.monthly_rent,))
        last_rent[side] = offer.monthly_rent
        stuck = rnd >= 4 and last_rent["seeker"] is not None and last_rent["leaver"] != last_rent["seeker"]
        text, more, verdict = clean(side, mv.message, offer, stuck, full=True)
        log(Turn(round=rnd, side=side, action=mv.action, offer=offer, message=text, flags=flags + fixes + more))
        on_table = offer

        if rnd >= referee.MAX_ROUNDS * 2:
            break
        side = "leaver" if side == "seeker" else "seeker"
        situation = f"The other agent says: \"{text}\"\n{describe(on_table)}\nRound {rnd // 2 + 1} of {referee.MAX_ROUNDS}."
        if verdict.suggestion:
            note = f"Referee suggestion: {verdict.suggestion}"
            log(Turn(round=rnd, side="referee", action="suggest", message=note))
            situation += f"\n{note}"

    log(Turn(round=referee.MAX_ROUNDS * 2, side="referee", action="stop", message="No deal within the round limit."))
    return None, turns
