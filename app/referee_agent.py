"""The referee agent: Claude Sonnet reviews every move before the other side sees it.

It sits on top of the hard rules in referee.py. Those clamp numbers and block out-of-limit accepts no matter what;
this agent adds judgment: indirect hints at a private limit, pressure tactics, fair-housing problems, and a
neutral compromise when the two agents are stuck.
"""

from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel, Field
from strands import Agent
from strands.models import BedrockModel

from . import referee
from .models import Leaver, Offer, Seeker

MODEL_ID = os.environ.get("REFEREE_MODEL", "us.anthropic.claude-sonnet-5-5")
REGION = os.environ.get("BEDROCK_REGION", "us-east-1")


class Verdict(BaseModel):
    message: str = Field(description="The message to deliver: unchanged if it was fine, otherwise rewritten to fix the issues")
    issues: list[str] = Field(default=[], description="Short labels for anything you changed, e.g. 'hinted at budget'")
    suggestion: Optional[str] = Field(default=None, description="A neutral compromise for both agents, only when they are stuck")
    suggested_rent: Optional[int] = Field(default=None, description="The monthly rent in your suggestion, if any")


SYSTEM = """You are the neutral referee between two students' sublease agents. You see every message before the other
side does. You know both students' private limits so you can catch leaks. Never reveal either limit, directly or
indirectly, in anything you write.

For each message:
- If it reveals or hints at the sender's private limit (e.g. "my max is a bit over 850", "I can go a little lower"
  with a number near the floor), rewrite it to remove the hint while keeping the offer.
- If it uses pressure tactics (fake deadlines, guilt, threats), rewrite it to be plain and friendly.
- If it mentions or asks about race, religion, national origin, sex, disability or family status, remove that part
  (Fair Housing Act). Lifestyle rules like no smoking or quiet hours are fine.
- Otherwise return the message unchanged with no issues.
Only when asked whether they are stuck: if the last offers are close, suggest one neutral compromise (rent and dates)
that both students' limits allow, without explaining why it works for either side."""


class RefereeAgent:
    def __init__(self, leaver: Leaver, seeker: Seeker, model_id: str = MODEL_ID):
        self.leaver, self.seeker = leaver, seeker
        limits = (f"PRIVATE (never reveal): leaver's lowest rent ${leaver.floor_rent}/month, dates "
                  f"{leaver.available_from} to {leaver.available_to} ± {leaver.flex_days} days. Seeker's highest rent "
                  f"${seeker.max_rent}/month, needs {seeker.need_from} to {seeker.need_to} ± {seeker.flex_days} days.")
        model = BedrockModel(model_id=model_id, region_name=REGION, max_tokens=4000)
        self.agent = Agent(model=model, system_prompt=f"{SYSTEM}\n\n{limits}", callback_handler=None, name="referee-agent")

    def review(self, side: str, message: str, offer: Optional[Offer], stuck: bool = False,
               last_offers: str = "") -> Verdict:
        who = "leaving student's agent" if side == "leaver" else "arriving student's agent"
        ask = f"Message from the {who}: \"{message}\"\nOffer attached: {offer.model_dump_json() if offer else 'none'}"
        if stuck:
            ask += f"\nThey are stuck. Last public offers: {last_offers}. Suggest one compromise if one fits both limits."
        v = self.agent(ask, structured_output_model=Verdict).structured_output
        return self.safe(v)

    def safe(self, v: Verdict) -> Verdict:
        """Never trust the referee's own text blindly: the hard rules re-scrub it and check any suggested rent."""
        secrets = [self.leaver.floor_rent, self.seeker.max_rent]
        v.message, _ = referee.scrub(v.message, secrets)
        if v.suggestion:
            v.suggestion, _ = referee.scrub(v.suggestion, secrets)
            zone = referee.zone_of_agreement(self.leaver, self.seeker)
            if not v.suggested_rent or not zone or not zone[0] <= v.suggested_rent <= zone[1]:
                v.suggestion = v.suggested_rent = None  # drop a suggestion either student couldn't accept
        return v
