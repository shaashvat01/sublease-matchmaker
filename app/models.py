"""Data models: private profiles, the public card, and the messages agents exchange."""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Leaver(BaseModel):
    """A student with a place to sublease. Fields marked private never leave their own agent."""

    id: str
    discord_id: Optional[int] = None
    name: str
    neighborhood: str
    address: str  # private until both say "deal"
    zip: str
    lat: float
    lng: float
    available_from: date
    available_to: date
    flex_days: int = 0  # private: how far the dates can bend
    asking_rent: int  # monthly, USD
    floor_rent: int  # private: lowest monthly rent they'd accept
    deposit: int = 0
    utilities_included: bool = False
    furnished: bool = True
    room_type: str = "private room"
    house_rules: list[str] = []
    roommate_approval: bool = False  # roommates must OK the subtenant


class Seeker(BaseModel):
    """A student looking for a place, usually arriving for an internship."""

    id: str
    discord_id: Optional[int] = None
    name: str
    office_name: str
    office_lat: float
    office_lng: float
    need_from: date
    need_to: date
    flex_days: int = 0  # private
    target_rent: int  # what they'd like to pay
    max_rent: int  # private: the most they can pay
    must_haves: list[str] = []
    deal_breakers: list[str] = []


class Card(BaseModel):
    """What the whole board sees. No exact address, no private limits."""

    leaver_id: str
    neighborhood: str
    available: str  # e.g. "May 20 – Aug 10"
    rent: int
    room_type: str
    furnished: bool
    utilities_included: bool
    house_rules: list[str]
    verified: bool = False


class Offer(BaseModel):
    move_in: date
    move_out: date
    monthly_rent: int = Field(description="Monthly rent in USD")
    deposit: int = Field(default=0, description="Refundable deposit in USD")
    utilities_included: bool = False
    notes: str = Field(default="", description="Short terms or conditions, plain words")


class Move(BaseModel):
    """One negotiation turn from an agent."""

    action: Literal["propose", "counter", "accept", "reject"]
    offer: Optional[Offer] = Field(default=None, description="Required for propose and counter")
    message: str = Field(description="One or two friendly sentences the other agent will read")
    private_note: str = Field(default="", description="Why you made this move; only your own student sees it")


class Turn(BaseModel):
    """A move after the referee checked it, as logged and shown."""

    round: int
    side: Literal["leaver", "seeker", "referee"]
    action: str
    offer: Optional[Offer] = None
    message: str
    flags: list[str] = []
