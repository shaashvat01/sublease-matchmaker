# Sublease Matchmaker: Track 2 plan (draft)

## The problem
Every semester and summer, two groups of students are looking for each other and can't find each other:
- **Leavers:** going on an internship, study abroad or co-op. They're paying rent on an empty room and want someone to take it over.
- **Seekers:** arriving for an internship or a term. They need a furnished room for exact dates, near the office, on a budget.

Today they meet through Facebook groups, GroupMe threads and Reddit posts: hundreds of messages, mismatched dates,
scams, and the same five questions asked over and over. Each side has private limits they don't want to post
publicly (the lowest rent they'd accept, the most they can pay, how flexible their dates really are).

## Who's involved (one agent each)
| Human | Their agent knows (private) | Their agent may publish (public card) |
|---|---|---|
| Leaver | Address, rent, **lowest acceptable rent**, exact dates and **how much they can bend**, house rules, roommates, photos, landlord's rules on subletting | Neighborhood, rough dates, rent band, furnished?, room type, photos (blurred or partial) |
| Seeker | Office address, **top budget**, exact dates and flexibility, deal-breakers (pets, smoking, parking), arrival logistics | Target area, rough dates, budget band, "verified student" badge |
| Roommates (optional) | Their own approval rules ("no smoking", "under 3 months is fine") | Nothing |

Agents represent their own human only, and never reveal private limits to the other side.

## The flow
```
1. Intake (private DM)   leaver/seeker chats with their own agent → structured profile
2. Verify                 one-time code to the student's .edu email → "verified student" badge
3. Publish                leaver's agent posts a privacy-safe card to the shared board
4. Match                  seeker's agent scores cards: date overlap, budget fit, commute time to the office
5. Open a negotiation     the seeker's agent opens a negotiation room with the leaver's agent (both humans pinged:
                          "Found a match, 0.6 mi from your office, Jun 1–Aug 15. Let my agent negotiate?")
6. Negotiate (A2A)        structured offers and counteroffers inside each human's private limits:
                            - dates: partial overlap → prorated rent, or a nudged move-in date
                            - price: meet between the leaver's floor and the seeker's ceiling
                            - terms: deposit, utilities, furniture, house rules, roommate approval
7. Human checkpoints      each agent must get its human's yes before it:
                            - reveals more detail (exact address, real photos, name)
                            - commits to a price or dates
                            - shares contact information
8. Close                  both say yes → the bot opens a private group with both students (plus the roommates if needed),
                          posts a sublease summary and checklist (landlord consent, deposit, move-in photos,
                          payment method), and sets reminders
```

## What gets shared, and when
| Stage | Shared |
|---|---|
| 0: public board | Neighborhood, date range, rent band, room type, verified badge |
| 1: negotiating | Exact dates, the asking rent and offers, house rules, more photos. Never the private limits |
| 2: both said "interested" | Street (not unit), the full photo set, first names |
| 3: both said "deal" | Full address, contact info, group chat |

## What makes this a strong Track 2 entry (the judges' brief)
- **Conflicting constraints:** dates that only partly overlap, price gaps, house rules versus seeker needs, and the roommates' veto.
- **What they share:** a progressive disclosure ladder, with private limits never revealed.
- **When they ask their students to confirm:** before each disclosure step, any price or date commitment, and contact sharing.
- **"We need this":** every campus has a sublease Facebook group full of chaos and scams.

## Safety and fairness rules (built in)
- Agents never filter or rank on protected characteristics (race, religion, national origin, sex, familial status,
  disability). That follows the Fair Housing Act. Lifestyle rules (smoking, pets, quiet hours) are fine.
- No money moves through the bot. It warns about common scams (wiring a deposit before a tour, "I'm abroad,
  can't show it").
- It reminds the leaver to get landlord consent, and links to a template rather than giving legal advice.

## Tech (from research, 2026-10-24)

### Platform: Discord (recommended), with Slack as the fallback
- One "Campus Sublets" server:
  - `#listings`: public cards as embeds
  - `#negotiation-log`: the agents' bargaining, live, for the demo
  - **private threads** per match: the bot creates the thread and adds both students. Private threads are visible
    only to invited members
- DMs with the bot are each student's private agent. Buttons and modals handle the human confirmations.
- The catch: Discord only delivers ordinary messages and DMs over its persistent gateway websocket, so the bot is one
  always-on process (discord.py). That is fine for a prototype, and simpler than Lambda queues.
- Why not Slack, even though it is all-HTTP and creates multi-person DMs natively: students don't live in Slack. Keep it
  as the fallback if Discord blocks us.
- Ruled out: WhatsApp (no buttons in groups, business verification, new charges), iMessage (Sendblue $100/mo, or a
  Mac-hosted bridge), Telegram (bots can't create groups; low US student use).

### Agents: Strands Agents (Python) + Claude on Bedrock
- One Strands agent per student, holding only its own human's private profile.
- Typed messages via `structured_output_model` (Pydantic `Offer`), plus `HumanInTheLoop` interrupts for the confirmations.
- Model: Claude Sonnet 5.5 (`us.anthropic.claude-sonnet-5-5`, us-east-1) for every agent: intake, both negotiators and the
  referee. No Haiku.
- **Referee agent (Sonnet):** reviews each message for indirect leaks, pressure tactics and fair-housing issues, and
  suggests compromises when stuck.
- **Hard rules in plain code, under the referee agent:** it checks every offer against the sender's private limits, caps the
  rounds, strips private fields from what the other agent sees, and blocks protected-class wording on cards.
- Stretch: expose each agent as an A2A service (`strands-agents[a2a]`), so "agent-to-agent" means a real protocol.

### Negotiation protocol
```
Offer   { move_in, move_out, monthly_rent, prorated_total, deposit, utilities_included, furniture, notes }
Action  propose | counter | accept | reject | ask_human
Rules   seeker never offers above its ceiling; leaver never accepts below its floor (referee-enforced)
        at most 6 rounds; if stuck, the referee suggests the midpoint of the overlapping range
        any commit or disclosure step → ask_human → Discord button → resume
```

### APIs
| Need | Choice | Notes |
|---|---|---|
| Commute time to the office | Distance from the listing to the office | |
| Geocoding | OpenStreetMap Nominatim (1 req/s) | |
| Rent fairness / scam flag | HUD Fair Market Rent API (Small Area FMR by ZIP) | Free with a HUD User token; flag rent far below FMR |
| .edu verification code | Amazon SES or Resend | |
| Listings | Entered by the students themselves | No usable listing APIs exist |

### Hosting and state
- The bot process runs on a small Lightsail ($5/mo) or EC2 instance (or a laptop during the demo).
- DynamoDB (or SQLite for the prototype) for profiles, cards, negotiations and audit logs.
- S3 for listing photos.
- Avoid App Runner (closed to new customers as of 2026).

## Demo script (target 2 minutes)
1. A leaver (Tempe, leaving May 20–Aug 10, wants $850, would accept $750) and a seeker (summer intern, Jun 1–Aug 15,
   budget up to $900, office in Tempe) each DM their agent.
2. The negotiation channel shows the two agents bargaining live: the date mismatch gets resolved with a prorate, and
   they settle at $820.
3. Each human gets a confirm button, both tap yes, and the private group opens with the summary and checklist.
