"""The intake agent: a short DM conversation that turns a student's plain words into a profile."""

from __future__ import annotations

import os
import time
from datetime import date
from typing import Literal, Optional

import httpx
from pydantic import BaseModel, Field
from strands import Agent
from strands.models import BedrockModel

MODEL_ID = os.environ.get("INTAKE_MODEL", "us.anthropic.claude-sonnet-5-5")
REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "sublease-matchmaker/0.1 (Cubbie Hackathon prototype)"


class LeaverDraft(BaseModel):
    name: str = Field(description="First name only")
    neighborhood: str
    address: str = Field(description="Street address including city and state")
    zip: str
    available_from: date
    available_to: date
    flex_days: int = 0
    asking_rent: int
    floor_rent: int = Field(description="Lowest monthly rent they'd accept (kept private)")
    deposit: int = 0
    utilities_included: bool = False
    furnished: bool = True
    room_type: str = "private room"
    house_rules: list[str] = []
    roommate_approval: bool = False


class SeekerDraft(BaseModel):
    name: str = Field(description="First name only")
    office_name: str = Field(description="Where they'll work or study, as an address or well-known place with city")
    need_from: date
    need_to: date
    flex_days: int = 0
    target_rent: int
    max_rent: int = Field(description="Most they can pay per month (kept private)")
    must_haves: list[str] = []
    deal_breakers: list[str] = []


class IntakeReply(BaseModel):
    reply: str = Field(description="Your next short message to the student (one question at a time)")
    role: Optional[Literal["leaver", "seeker"]] = None
    done: bool = Field(default=False, description="True only when every required field is known")
    leaver: Optional[LeaverDraft] = None
    seeker: Optional[SeekerDraft] = None


SYSTEM = f"""You are a student's personal sublease agent, chatting in Discord DMs. Today is {date.today()}.
First find out whether they are LEAVING (they have a place to sublease) or ARRIVING (they need a place, often for an internship).
Then collect the fields for their profile, one short question at a time, in a friendly texting tone.
Ask for their private limit plainly and explain it stays private: for leavers, the lowest monthly rent they'd accept;
for seekers, the most they can pay. Your agent never shows it to anyone.
Ask how flexible their dates are (in days). Assume the next upcoming summer when they give dates without a year.
Never ask about or record race, religion, national origin, sex, disability or family status. If they volunteer a
preference about those, explain kindly that housing listings can't include it, and leave it out.
Lifestyle rules (smoking, pets, quiet hours, guests) are fine.
When every required field is known, set done=true, fill in leaver or seeker, and in reply summarize the profile in a
few short lines (say which numbers are private) and ask them to confirm with the button."""


class Intake:
    def __init__(self):
        model = BedrockModel(model_id=MODEL_ID, region_name=REGION, max_tokens=4000)
        self.agent = Agent(model=model, system_prompt=SYSTEM, callback_handler=None, name="intake-agent")

    def chat(self, text: str) -> IntakeReply:
        return self.agent(text, structured_output_model=IntakeReply).structured_output


def geocode(query: str) -> Optional[tuple[float, float]]:
    """Address or place name → (lat, lng), with OpenStreetMap Nominatim.

    Students describe places loosely ("the State Farm office near Tempe Town Lake"), so try a few simpler
    versions of the query before giving up.
    """
    parts = [p.strip() for p in query.split(",")]
    tail = ", ".join(parts[1:])
    variants = [query]
    if " near " in parts[0]:
        variants.append(parts[0].split(" near ", 1)[1] + (f", {tail}" if tail else ""))
    variants.append(parts[0].replace(" office", "") + (f", {tail}" if tail else ""))
    if tail:
        variants.append(tail)  # the city, as a last resort
    for q in dict.fromkeys(variants):
        point = nominatim(q)
        if point:
            return point
    return None


def nominatim(query: str) -> Optional[tuple[float, float]]:
    """OpenStreetMap Nominatim: at most 1 request per second, with an identifying User-Agent."""
    try:
        time.sleep(1)
        r = httpx.get(NOMINATIM, params={"q": query, "format": "json", "limit": 1},
                      headers={"User-Agent": USER_AGENT}, timeout=15)
        r.raise_for_status()
        hits = r.json()
        return (float(hits[0]["lat"]), float(hits[0]["lon"])) if hits else None
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        return None
