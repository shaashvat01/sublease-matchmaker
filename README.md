# Sublease Matchmaker

Personal AI agents that negotiate student subleases with each other, on Discord. Built for Track 2 (Agent-to-Agent
Coordination) of the [Cubbie Hackathon](https://hackathon.cubbie.ai).

Every summer, students leaving for internships pay rent on empty rooms, while students arriving for internships
scroll through chaotic Facebook groups looking for one. Here, each student DMs their own agent once. The agents find
the matches, negotiate dates and rent within each student's private limits, and introduce the two students only after
both say yes.

## How it works
1. **Intake (private DM).** Each student tells their agent about their place or their internship in plain words. The
   agent asks one question at a time, including a private limit: the lowest rent for a leaver, the highest budget for
   a seeker.
2. **Listing.** A privacy-safe card goes to `#listings`: neighborhood, dates, asking rent, rules. No address, no limits.
3. **Matching.** The seeker's agent ranks listings by date overlap, budget fit and commute time to the office.
4. **Ask first.** The seeker taps *Let my agent negotiate*, and the leaver taps *Yes, negotiate*.
5. **Agent-to-agent negotiation**, live in `#negotiation-log`: offers and counteroffers, prorated partial stays, date
   nudges.
6. **Both confirm.** Each student gets the terms and taps *Confirm deal*. Nothing is shared before that.
7. **Introduction.** A private thread opens for just those two students, with the address, the agreed terms and a
   safety checklist.

### The referee
A Claude Sonnet referee agent (`app/referee_agent.py`) reviews every message before the other side sees it. It catches
indirect hints at a private limit, pressure tactics and fair-housing problems, and suggests a neutral compromise
when the agents are stuck. Underneath it, hard rules in plain code (`app/referee.py`) check every move whatever any
model says:
- It clamps offers to the sender's own limits, and blocks an agent from accepting outside them.
- It redacts any private number that slips into a message.
- It strips protected-class wording from listings and messages (Fair Housing Act, 42 U.S.C. 3604(c)).
- It caps the rounds, and drops any referee suggestion that falls outside either student's limits.

### What gets shared, when
| Stage | Visible |
|---|---|
| Listed | Neighborhood, dates, asking rent, rules, verified badge |
| Negotiating | Offers (dates, rent, deposit, terms). Never the private limits |
| Both confirmed | Name, full address, a private thread together |

## Stack
- Discord bot: discord.py; DMs, buttons, private threads.
- Strands Agents with Claude Sonnet 5.5 on Amazon Bedrock for every agent (intake, both negotiators, referee), using
  typed structured output (`Move`, `Offer`, `Verdict`).
- Geocoding: OpenStreetMap Nominatim; commute time from distance to the office.
- SQLite for state.

## Run it
```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env              # fill in DISCORD_TOKEN
.venv/bin/python -m pytest -q     # referee tests
.venv/bin/python sim.py           # a negotiation in the terminal, no Discord needed
.venv/bin/python bot.py           # the Discord bot
```
AWS credentials with Bedrock access to Claude Sonnet 5.5 in `us-east-1` are required.

Add the bot to any server and it sets up `#listings`, `#negotiation-log` and `#matches` there. In Discord,
`/sublease` opens your private agent in DMs. Students are matched with listings from their own server.

## Safety
- No money moves through the bot.
- The checklist covers landlord consent, roommate approval, touring before paying, and a written sublease.
- Scam warnings follow FTC guidance: wire, gift card or crypto payments, "I'm abroad", rent far below nearby rents.
