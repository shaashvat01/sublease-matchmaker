"""Discord bot: each student's DMs are their private agent; the server shows listings, the negotiation log and
private match threads.

    .venv/bin/python bot.py      # needs DISCORD_TOKEN and GUILD_ID in .env
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

from app import intake, matching, referee, store
from app.models import Leaver, Seeker, Turn
from app.negotiation import negotiate

load_dotenv()
GUILD = discord.Object(id=int(os.environ["GUILD_ID"]))
CHANNELS = ("listings", "negotiation-log", "matches")
BLUE, GREEN, RED = 0x0A84FF, 0x30D158, 0xFF453A

intents = discord.Intents.default()  # DMs carry message content without the privileged intent
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
sessions: dict[int, intake.Intake] = {}  # discord user id -> intake conversation in progress


# ---------- helpers ----------

async def channel(name: str) -> discord.TextChannel:
    guild = client.get_guild(GUILD.id)
    found = discord.utils.get(guild.text_channels, name=name)
    return found or await guild.create_text_channel(name)


async def dm(discord_id: int | None, *args, **kwargs):
    if discord_id:
        user = client.get_user(discord_id) or await client.fetch_user(discord_id)
        return await user.send(*args, **kwargs)


def card_embed(l: Leaver, extra: str = "") -> discord.Embed:
    c = matching.make_card(l, verified=store.is_verified(l.id))
    e = discord.Embed(title=f"{c.room_type.capitalize()} · {c.neighborhood}", color=BLUE, description=extra or None)
    e.add_field(name="Dates", value=c.available)
    e.add_field(name="Rent", value=f"${c.rent}/mo")
    e.add_field(name="Utilities", value="included" if c.utilities_included else "extra")
    e.add_field(name="Furnished", value="yes" if c.furnished else "no")
    e.add_field(name="House rules", value=", ".join(c.house_rules) or "none")
    e.add_field(name="Student", value="✅ verified" if c.verified else "not verified yet")
    return e


def terms(o) -> str:
    return (f"{o.move_in:%b %d} → {o.move_out:%b %d} · **${o.monthly_rent}/mo** (≈${referee.stay_total(o)} total) · "
            f"deposit ${o.deposit} · utilities {'included' if o.utilities_included else 'extra'}")


def turn_text(t: Turn) -> str:
    who = {"seeker": "🧳 Arriving student's agent", "leaver": "🏠 Leaving student's agent", "referee": "⚖️ Referee"}[t.side]
    lines = [f"**{who}** · {t.action}" + (f" · round {(t.round + 1) // 2}" if t.side != "referee" else "")]
    if t.offer:
        lines.append(terms(t.offer))
    lines.append(f"> {t.message}")
    if t.flags:
        lines.append("🛡️ referee: " + "; ".join(t.flags))
    return "\n".join(lines)


CHECKLIST = """**Before anyone pays anything**
☐ Landlord or leasing office has approved the sublease in writing
☐ Roommates have met and approved the subtenant (if the listing needs it)
☐ Tour the place (or a live video tour) before sending money
☐ Sign a written sublease with the dates, rent, deposit and utilities above
☐ Pay through a traceable method; take move-in photos
⚠️ Scam signs: wire, gift card or crypto payment · "I'm abroad, can't show it" · rent far below nearby rents"""


# ---------- profile confirmation ----------

class ConfirmProfile(discord.ui.View):
    def __init__(self, reply: intake.IntakeReply):
        super().__init__(timeout=None)
        self.reply = reply

    @discord.ui.button(label="Looks right", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        uid, r = interaction.user.id, self.reply
        if r.role == "leaver":
            point = await asyncio.to_thread(intake.geocode, r.leaver.address)
            if not point:
                return await interaction.followup.send("I couldn't find that address on the map. Can you send it with the city and state?")
            p = Leaver(id=store.new_id("L"), discord_id=uid, lat=point[0], lng=point[1], **r.leaver.model_dump())
            store.save_profile(p)
            sessions.pop(uid, None)
            await (await channel("listings")).send(embed=card_embed(p))
            await interaction.followup.send("You're listed 🎉 Only the neighborhood, dates and asking rent are public. "
                                            "I'll message you when a student's agent wants to negotiate.")
        else:
            point = await asyncio.to_thread(intake.geocode, r.seeker.office_name)
            if not point:
                return await interaction.followup.send("I couldn't find that office on the map. Can you send its street address?")
            p = Seeker(id=store.new_id("S"), discord_id=uid, office_lat=point[0], office_lng=point[1], **r.seeker.model_dump())
            store.save_profile(p)
            sessions.pop(uid, None)
            await show_matches(interaction.user, p)
        self.stop()

    @discord.ui.button(label="Change something", style=discord.ButtonStyle.secondary)
    async def edit(self, interaction: discord.Interaction, _):
        await interaction.response.send_message("Sure, tell me what to change.")


async def show_matches(user: discord.abc.User, seeker: Seeker):
    ranked = await asyncio.to_thread(matching.rank, store.leavers(), seeker)
    if not ranked:
        return await user.send("No listings fit your dates and budget yet. I'll keep looking and message you when one does.")
    await user.send(f"Here are your best matches, {seeker.name}. Pick one and my agent will negotiate for you. "
                    "It never reveals your max budget.")
    for m in ranked[:3]:
        l = store.profile(m["leaver_id"])
        extra = f"**{m['commute_min']} min** to your office · covers {round(m['coverage'] * 100)}% of your dates"
        await user.send(embed=card_embed(l, extra), view=StartNegotiation(l.id, seeker.id))


# ---------- negotiation ----------

class StartNegotiation(discord.ui.View):
    def __init__(self, leaver_id: str, seeker_id: str):
        super().__init__(timeout=None)
        self.leaver_id, self.seeker_id = leaver_id, seeker_id

    @discord.ui.button(label="Let my agent negotiate", style=discord.ButtonStyle.primary)
    async def go(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        await interaction.response.edit_message(view=self)
        leaver, seeker = store.profile(self.leaver_id), store.profile(self.seeker_id)
        nid = store.new_negotiation(leaver.id, seeker.id)
        await interaction.followup.send("Asking the other student's agent. Watch it live in #negotiation-log.")
        if leaver.discord_id:
            ask = (f"A student's agent wants to negotiate for your place: they need **{seeker.need_from:%b %d} – "
                   f"{seeker.need_to:%b %d}**{' (verified student)' if store.is_verified(seeker.id) else ''}. "
                   "Let my agent negotiate for you? Your lowest rent stays private.")
            await dm(leaver.discord_id, ask, view=AllowNegotiation(nid))
        else:
            await run_negotiation(nid)


class AllowNegotiation(discord.ui.View):
    def __init__(self, nid: str):
        super().__init__(timeout=None)
        self.nid = nid

    @discord.ui.button(label="Yes, negotiate", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(content="Negotiating now. Watch it live in #negotiation-log.", view=None)
        await run_negotiation(self.nid)

    @discord.ui.button(label="No thanks", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(content="No problem, I declined.", view=None)
        row = store.negotiation(self.nid)
        store.update_negotiation(self.nid, status="declined")
        await dm(store.profile(row["seeker_id"]).discord_id, "That listing's owner passed this time. Want to try another match?")


async def run_negotiation(nid: str):
    row = store.negotiation(nid)
    leaver, seeker = store.profile(row["leaver_id"]), store.profile(row["seeker_id"])
    card = matching.make_card(leaver, verified=store.is_verified(leaver.id))
    log = await channel("negotiation-log")
    await log.send(f"━━━━━━━━━━\n**New negotiation** · {card.room_type} in {card.neighborhood} · listed "
                   f"{card.available} at ${card.rent}/mo")
    loop = asyncio.get_running_loop()

    def on_turn(t: Turn):
        asyncio.run_coroutine_threadsafe(log.send(turn_text(t)), loop).result()

    store.update_negotiation(nid, status="negotiating")
    deal, _ = await asyncio.to_thread(negotiate, leaver, seeker, card, on_turn)
    if not deal:
        store.update_negotiation(nid, status="no_deal")
        await log.send("❌ No deal.")
        await dm(seeker.discord_id, "Our agents couldn't find a deal inside your limits for that one. Want to try another match?")
        return await dm(leaver.discord_id, "No deal with that student this time. Your listing stays up.")

    store.update_negotiation(nid, status="agreed", deal=deal)
    await log.send("🤝 The agents reached terms. Waiting for both students to confirm.")
    e = discord.Embed(title="Your agent reached a deal", description=terms(deal), color=GREEN)
    if deal.notes:
        e.add_field(name="Notes", value=deal.notes[:1000])
    e.set_footer(text="Nothing is final until you both confirm. Confirming shares your contact and the full address.")
    await dm(seeker.discord_id, embed=e, view=ConfirmDeal(nid, "seeker"))
    if leaver.discord_id:
        await dm(leaver.discord_id, embed=e, view=ConfirmDeal(nid, "leaver"))
    else:
        store.update_negotiation(nid, leaver_ok=1)


class ConfirmDeal(discord.ui.View):
    def __init__(self, nid: str, side: str):
        super().__init__(timeout=None)
        self.nid, self.side = nid, side

    @discord.ui.button(label="Confirm deal", style=discord.ButtonStyle.success)
    async def ok(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(content="Confirmed ✅", view=None)
        store.update_negotiation(self.nid, **{f"{self.side}_ok": 1})
        row = store.negotiation(self.nid)
        if row["leaver_ok"] and row["seeker_ok"] and not row["thread_id"]:
            await open_match_thread(self.nid)
        else:
            await interaction.followup.send("Waiting for the other student to confirm.")

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(content="Declined. Nothing was shared.", view=None)
        store.update_negotiation(self.nid, status="declined")


async def open_match_thread(nid: str):
    row = store.negotiation(nid)
    leaver, seeker, deal = store.profile(row["leaver_id"]), store.profile(row["seeker_id"]), store.deal_of(row)
    matches = await channel("matches")
    thread = await matches.create_thread(name=f"Sublease · {leaver.neighborhood}"[:90],
                                         type=discord.ChannelType.private_thread, invitable=False)
    for uid in (leaver.discord_id, seeker.discord_id):
        if uid:
            await thread.add_user(discord.Object(id=uid))
    store.update_negotiation(nid, status="closed", thread_id=thread.id)
    people = " & ".join(f"<@{u}>" for u in (leaver.discord_id, seeker.discord_id) if u)
    e = discord.Embed(title=f"🎉 {seeker.name}, meet {leaver.name}", color=GREEN, description=terms(deal))
    e.add_field(name="Address", value=leaver.address, inline=False)
    if leaver.house_rules:
        e.add_field(name="House rules", value=", ".join(leaver.house_rules), inline=False)
    if leaver.roommate_approval:
        e.add_field(name="Roommates", value="The roommates need to meet and approve before it's final.", inline=False)
    await thread.send(f"{people} your agents agreed and you both confirmed. Only you two can see this thread.", embed=e)
    await thread.send(CHECKLIST)
    await (await channel("negotiation-log")).send("✅ Both students confirmed. A private thread is open for them.")


async def post_listings():
    """Refresh #listings so it shows exactly the current listings."""
    listings = await channel("listings")
    async for msg in listings.history(limit=200):
        if msg.author == client.user:
            await msg.delete()
    for l in store.leavers():
        await listings.send(embed=card_embed(l))


# ---------- DMs and commands ----------

@client.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is not None:
        return
    uid, text = message.author.id, message.content.strip()
    if text.lower() in ("reset", "start over"):
        sessions.pop(uid, None)
        return await message.channel.send("Fresh start. Are you leaving a place, or arriving and looking for one?")
    existing = store.profile_of(uid)
    if existing and uid not in sessions:
        if isinstance(existing, Seeker) and "match" in text.lower():
            return await show_matches(message.author, existing)
        return await message.channel.send("You already have a profile. Say **matches** to see listings again, "
                                          "or **reset** to start over.")
    session = sessions.setdefault(uid, intake.Intake())
    async with message.channel.typing():
        reply = await asyncio.to_thread(session.chat, text)
    if reply.done and (reply.leaver or reply.seeker):
        await message.channel.send(reply.reply, view=ConfirmProfile(reply))
    else:
        await message.channel.send(reply.reply)


@tree.command(name="sublease", description="Start talking to your private sublease agent (in DMs)", guild=GUILD)
async def sublease(interaction: discord.Interaction):
    await dm(interaction.user.id, "Hi! I'm your private sublease agent. Are you **leaving** a place this summer, "
                                  "or **arriving** and looking for one?")
    await interaction.response.send_message("Check your DMs 👋", ephemeral=True)


@client.event
async def on_ready():
    for name in CHANNELS:
        await channel(name)
    if not store.leavers():
        store.seed(Path(__file__).parent / "data" / "listings.json")
    await post_listings()
    await tree.sync(guild=GUILD)
    print(f"Ready as {client.user} in guild {GUILD.id}")


if __name__ == "__main__":
    client.run(os.environ["DISCORD_TOKEN"])
