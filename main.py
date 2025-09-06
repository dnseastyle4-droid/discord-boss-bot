# main.py — Final complete bot
import os
import re
import threading
import asyncio
from datetime import datetime, timedelta, timezone, time as dtime
from typing import List, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from flask import Flask

# -----------------------
# ENV / CONFIG
# -----------------------
TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
CHANNELS_ENV = os.getenv("CHANNELS", "")  # e.g. "123456789012345678,987654321098765432"
CHANNEL_IDS: List[int] = [int(x) for x in CHANNELS_ENV.split(",") if x.strip().isdigit()]
GUILD_RAW = os.getenv("GUILD_ID") or os.getenv("Enemies")
GUILD_ID = int(GUILD_RAW) if GUILD_RAW and GUILD_RAW.isdigit() else None

if not TOKEN:
    raise RuntimeError("Set DISCORD_TOKEN (or TOKEN) env var.")
if not CHANNEL_IDS:
    raise RuntimeError("Set CHANNELS env var to comma-separated channel IDs.")

# use PH time (UTC+8)
TZ = timezone(timedelta(hours=8))

# -----------------------
# Flask keep-alive (for Render web service)
# -----------------------
flask_app = Flask("keepalive")

@flask_app.route("/")
def home():
    return "Boss bot alive!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask, daemon=True).start()

# -----------------------
# Bot & intents
# -----------------------
intents = discord.Intents.default()
# slash commands don't need message_content; keep minimal
bot = commands.Bot(command_prefix="!", intents=intents)
# remove default help to avoid conflict
try:
    bot.remove_command("help")
except Exception:
    pass

# -----------------------
# Boss Lists (from your requests)
# -----------------------
WORLD_BOSSES_RAW = {
    "Venatus": 10, "Viorent": 10, "Ego": 21, "Livera": 24, "Araneo": 21,
    "Undomiel": 24, "Lady Dalia": 18, "General Aquileus": 29, "Amentis": 29,
    "Baron Braudmore": 32, "Supore": 62, "Asta": 62, "Secreta": 62, "Ordo": 62,
    "Gareth": 32, "Shuliar": 35, "Larba": 35, "Catena": 35, "Titore": 37,
    "Duplican": 48, "Metus": 48, "Wannitas": 48
}

SCHEDULED_BOSSES_RAW = {
    "Clemantis": [("monday", "11:30"), ("thursday", "19:00")],
    "Saphirus":  [("sunday", "17:00"), ("tuesday", "11:30")],
    "Neutro":    [("tuesday", "19:00"), ("thursday", "11:30")],
    "Thymele":   [("monday", "19:00"), ("wednesday", "11:30")],
    "Milavy":    [("saturday", "15:00")],
    "Ringor":    [("saturday", "17:00")],
    "Roderick":  [("friday", "19:00")],
    "Auraq":     [("sunday", "21:00"), ("wednesday", "21:00")],
    "Chailflock":[("saturday", "22:00")]
}

UNIQUE_RAW = [
    "Alarak", "Black Wedge", "Outlaw Kaiser", "Screaming Wings", "Suspicious Wizard",
    "Dark Apparition", "Brutal Butcher", "Corrupted Shellbug", "Secret Creation",
    "Magic Puppet", "Wizard's Puppet", "Lamia Shaman", "Angusto",
    "Berserk Thardus", "Ancient Thardus", "Charging Thardus",
    "Desert Golem", "Ancient Turtle", "Protector of the Ruins", "Black Hand",
    "Ancient Protector", "Intikam", "Desert Protector",
    "Blood Mother", "Decoy", "Ghost Webber", "Shadow Webber",
    "Escort Leader Maximus", "Fortuneteller Ariel", "Priest Petroca",
    "Sylandra", "Halfmoon Stone Turtle", "Cobolt Blitz Captain",
    "Black Wings", "Forgotten Olive", "Deadman's Grow", "Cassandra",
    "Mutated Scorpion", "Berserk Higher Harpy", "Red Lizardman Patrol Captain",
    "Lyrian", "Durian", "Infected Kukri", "Straggler Brown", "Veridon",
    "Shaug Blitz Captain", "Shaug High-Ranking Wizard", "Shaug Patrol Captain",
    "Elder Lich", "Catena's Eye", "Elder Scorpius", "Catena's Servant",
    "Catena's Cry", "Catena's Ego", "Catena's Rage", "Catena's Sorrow"
]

DESTROYER_RAW = ["Ratan", "Parto", "Nedra"]

# -----------------------
# Normalization & display mapping
# -----------------------
def normalize(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.lower()
    s = s.replace("’", "'")
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

WORLD_BOSSES: Dict[str, int] = {}
SCHEDULED_BOSSES: Dict[str, List[tuple]] = {}
UNIQUE_MONSTERS = set()
DESTROYER_BOSSES = set()
DISPLAY_NAME: Dict[str, str] = {}

for k, hrs in WORLD_BOSSES_RAW.items():
    nk = normalize(k)
    WORLD_BOSSES[nk] = hrs
    DISPLAY_NAME[nk] = k

for k, sched in SCHEDULED_BOSSES_RAW.items():
    nk = normalize(k)
    SCHEDULED_BOSSES[nk] = sched
    DISPLAY_NAME[nk] = k

for k in UNIQUE_RAW:
    nk = normalize(k)
    UNIQUE_MONSTERS.add(nk)
    DISPLAY_NAME[nk] = k

for k in DESTROYER_RAW:
    nk = normalize(k)
    DESTROYER_BOSSES.add(nk)
    DISPLAY_NAME[nk] = k

ALL_KEYS = list(WORLD_BOSSES.keys()) + list(UNIQUE_MONSTERS) + list(SCHEDULED_BOSSES.keys()) + list(DESTROYER_BOSSES)

# -----------------------
# Runtime storage
# -----------------------
# pending: normalized -> {"display", "respawn": dt, "kind": "world"|"unique", "messages": [msg_id,...]}
pending: Dict[str, Dict] = {}
notified_scheduled = set()
notified_destroyer = set()
# message_cleanup: msg_id -> (channel_id, expiry_dt)
message_cleanup: Dict[int, tuple] = {}

# -----------------------
# Time helpers (PH time)
# -----------------------
def now_ph() -> datetime:
    return datetime.now(timezone.utc).astimezone(TZ)

def make_respawn_hours(h: int) -> datetime:
    return now_ph() + timedelta(hours=h)

def make_respawn_minutes(m: int) -> datetime:
    return now_ph() + timedelta(minutes=m)

# -----------------------
# Channel send helpers (with logging)
# -----------------------
async def send_to_channels_return(msg_text: str) -> List[discord.Message]:
    sent = []
    for cid in CHANNEL_IDS:
        ch = bot.get_channel(cid)
        if not ch:
            print(f"⚠️ Channel not found/cached: {cid}")
            continue
        try:
            m = await ch.send(msg_text)
            sent.append(m)
            print(f"✅ Sent message to channel {cid} (msg.id={m.id})")
        except Exception as e:
            print(f"❌ Failed to send to {cid}: {e}")
    return sent

async def send_to_channels(msg_text: str):
    await send_to_channels_return(msg_text)

# -----------------------
# Autocomplete helper
# -----------------------
async def name_autocomplete(interaction: discord.Interaction, current: str):
    cur = (current or "").lower()
    choices = []
    for k in ALL_KEYS:
        disp = DISPLAY_NAME.get(k, k.title())
        if cur in disp.lower() or cur in k:
            choices.append(app_commands.Choice(name=disp, value=disp))
            if len(choices) >= 25:
                break
    return choices

# -----------------------
# Parse PH time "HH:MM" into a datetime in PH timezone
# Rules:
#  - If tod is today and <= now -> use today at tod
#  - If tod > now (i.e. future today) assume time was yesterday (player reported kill before midnight)
#  - If parsing fails, return None
# -----------------------
def parse_ph_tod(tod_text: str) -> Optional[datetime]:
    try:
        now = now_ph()
        hh, mm = map(int, tod_text.split(":"))
        candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        # if candidate is in the future (later today), assume death was yesterday
        if candidate > now:
            candidate = candidate - timedelta(days=1)
        return candidate
    except Exception:
        return None

# -----------------------
# Slash commands
# -----------------------
@bot.tree.command(name="guide", description="Show quick usage & examples")
async def guide(interaction: discord.Interaction):
    text = (
        "**Boss Bot Guide**\n\n"
        "`/add <name> [HH:MM]` — Add a boss (optional PH-time time-of-death HH:MM). If no time provided, uses now.\n"
        "`/remove <name>` — Remove pending timer you added.\n"
        "`/status` — Show all pending timers and scheduled bosses within ~3 hours.\n\n"
        "Examples:\n"
        "`/add Alarak` — log unique (uses now)\n"
        "`/add Alarak 14:30` — log unique with PH time-of-death 14:30\n"
        "`/add Venatus 13:10` — log world boss with TOD (respawn = TOD + 10 hours)\n"
    )
    await interaction.response.send_message(text)

@bot.tree.command(name="add", description="Add a world boss or unique monster timer (optionally include PH time-of-death HH:MM)")
@app_commands.describe(name="Boss or monster name", tod="optional time of death in HH:MM (PH time)")
@app_commands.autocomplete(name=name_autocomplete)
async def add_cmd(interaction: discord.Interaction, name: str, tod: Optional[str] = None):
    disp = name.strip()
    # match display -> normalized
    norm = None
    for k, v in DISPLAY_NAME.items():
        if v.lower() == disp.lower():
            norm = k
            break
    if not norm:
        norm = normalize(disp)

    now = now_ph()

    # Destroyers: can't be added manually (auto windows)
    if norm in DESTROYER_BOSSES:
        await interaction.response.send_message(f"⚠️ {DISPLAY_NAME.get(norm,norm.title())} is a Destroyer — reminders run automatically.")
        return

    # Determine death time (TOD)
    if tod:
        tod_dt = parse_ph_tod(tod)
        if not tod_dt:
            await interaction.response.send_message("❌ Invalid TOD format. Use HH:MM (PH time).")
            return
        death_time = tod_dt
    else:
        death_time = now

    # Unique monsters (15 minutes respawn)
    if norm in UNIQUE_MONSTERS:
        if norm in pending:
            await interaction.response.send_message(f"⚠️ {DISPLAY_NAME[norm]} is already pending.")
            return
        resp = death_time + timedelta(minutes=15)
        pending[norm] = {"display": DISPLAY_NAME[norm], "respawn": resp, "kind": "unique", "messages": []}
        await interaction.response.send_message(f"✅ {DISPLAY_NAME[norm]} added — respawn at {resp.strftime('%I:%M %p')} (PH).")
        print(f"[add] unique {DISPLAY_NAME[norm]} added, respawn {resp.isoformat()}")
        return

    # World bosses (hours)
    if norm in WORLD_BOSSES:
        if norm in pending:
            await interaction.response.send_message(f"⚠️ {DISPLAY_NAME[norm]} is already pending.")
            return
        hours = WORLD_BOSSES[norm]
        resp = death_time + timedelta(hours=hours)
        pending[norm] = {"display": DISPLAY_NAME[norm], "respawn": resp, "kind": "world", "messages": []}
        await interaction.response.send_message(f"✅ {DISPLAY_NAME[norm]} added — respawn at {resp.strftime('%I:%M %p')} (PH) (in {hours}h).")
        print(f"[add] world {DISPLAY_NAME[norm]} added, respawn {resp.isoformat()}")
        return

    # Scheduled bosses: inform user
    if norm in SCHEDULED_BOSSES:
        await interaction.response.send_message(f"ℹ️ {DISPLAY_NAME.get(norm, norm.title())} is scheduled — it will be announced automatically when near spawn time.")
        return

    await interaction.response.send_message(f"❌ Unknown boss/monster: `{name}` — try autocomplete.")

@bot.tree.command(name="remove", description="Remove a pending world/unique timer you added")
@app_commands.describe(name="Boss or monster name")
@app_commands.autocomplete(name=name_autocomplete)
async def remove_cmd(interaction: discord.Interaction, name: str):
    disp = name.strip()
    norm = None
    for k, v in DISPLAY_NAME.items():
        if v.lower() == disp.lower():
            norm = k
            break
    if not norm:
        norm = normalize(disp)

    if norm in pending:
        # delete any posted reminder messages associated with this boss (unique messages stored)
        msgs = pending[norm].get("messages", [])
        for mid in msgs:
            ch_id, _ = message_cleanup.get(mid, (None, None))
            if ch_id:
                ch = bot.get_channel(ch_id)
                if ch:
                    try:
                        m = await ch.fetch_message(mid)
                        await m.delete()
                    except Exception:
                        pass
            message_cleanup.pop(mid, None)
        pending.pop(norm, None)
        notified_scheduled.discard(norm)
        notified_destroyer.discard(norm)
        await interaction.response.send_message(f"✅ Removed {DISPLAY_NAME.get(norm, norm.title())} from pending.")
    else:
        await interaction.response.send_message(f"❌ {DISPLAY_NAME.get(norm, norm.title())} is not pending.")

@bot.tree.command(name="status", description="Show pending timers and scheduled bosses within ~3 hours")
async def status_cmd(interaction: discord.Interaction):
    now = now_ph()
    lines = []

    # Pending (added)
    if pending:
        lines.append("**Pending (added)**:")
        for k, info in pending.items():
            resp = info["respawn"]
            mins = int((resp - now).total_seconds() // 60)
            if mins > 0:
                lines.append(f"- {info['display']} — in {mins} min (at {resp.strftime('%I:%M %p')})")
            else:
                lines.append(f"- {info['display']} — due now")
    else:
        lines.append("**Pending (added)**: none")

    # Scheduled within 3 hours (today)
    nearby = []
    weekday = now.strftime("%A").lower()
    for boss_key, scheds in SCHEDULED_BOSSES.items():
        for day, hhmm in scheds:
            if day != weekday:
                continue
            h, m = map(int, hhmm.split(":"))
            event_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            delta_h = (event_dt - now).total_seconds() / 3600
            if 0 < delta_h <= 3:
                nearby.append(f"- {DISPLAY_NAME.get(boss_key,boss_key.title())} at {hhmm} (in {delta_h:.1f} hr)")
    if nearby:
        lines.append("**Scheduled (within 3 hrs)**:")
        lines.extend(nearby)
    else:
        lines.append("**Scheduled (within 3 hrs)**: none")

    await interaction.response.send_message("\n".join(lines))

# -----------------------
# Background reminders loop (1 minute)
# -----------------------
@tasks.loop(minutes=1)
async def reminders_loop():
    now = now_ph()

    # 1) World bosses: notify ~2 minutes before respawn then remove (one-time)
    for key, info in list(pending.items()):
        if info["kind"] == "world":
            resp = info["respawn"]
            if now >= resp - timedelta(minutes=2):
                text = f"⚔️ **{info['display']}** will spawn in ~2 minutes! Prepare!"
                await send_to_channels(text)
                pending.pop(key, None)

    # 2) Unique monsters: notify ~1 minute before respawn then remove
    for key, info in list(pending.items()):
        if info["kind"] == "unique":
            resp = info["respawn"]
            # 1-minute warning: post reminder messages and track them for cleanup
            if now >= resp - timedelta(minutes=1) and now < resp:
                text = f"🔥 **{info['display']}** will spawn in ~1 minute! Get ready!"
                messages = await send_to_channels_return(text)
                expiry = now + timedelta(minutes=30)
                # record message ids both in global cleanup and in pending map (so /remove can delete them)
                for m in messages:
                    message_cleanup[m.id] = (m.channel.id, expiry)
                    pending[key].setdefault("messages", []).append(m.id)
            # expire pending entry after spawn time passes
            if now >= resp:
                pending.pop(key, None)

    # 3) Scheduled bosses: notify once when within 3 hours
    weekday = now.strftime("%A").lower()
    for boss_key, scheds in SCHEDULED_BOSSES.items():
        for day, hhmm in scheds:
            if day != weekday:
                continue
            h, m = map(int, hhmm.split(":"))
            event_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            delta_h = (event_dt - now).total_seconds() / 3600
            event_key = f"{boss_key}-{event_dt.date()}-{hhmm}"
            if 0 < delta_h <= 3 and event_key not in notified_scheduled:
                text = f"📢 Scheduled Boss **{DISPLAY_NAME.get(boss_key,boss_key.title())}** is coming at {hhmm} (in {delta_h:.1f} hr)."
                await send_to_channels(text)
                notified_scheduled.add(event_key)

    # 4) Destroyer windows: notify once per window per day (11:00-12:00 and 20:00-21:00)
    windows = [(dtime(11, 0), dtime(12, 0)), (dtime(20, 0), dtime(21, 0))]
    for boss_norm in DESTROYER_BOSSES:
        for start_t, end_t in windows:
            start_dt = now.replace(hour=start_t.hour, minute=start_t.minute, second=0, microsecond=0)
            end_dt = now.replace(hour=end_t.hour, minute=end_t.minute, second=0, microsecond=0)
            window_key = f"{boss_norm}-{start_dt.date()}-{start_t.strftime('%H%M')}"
            if start_dt <= now <= end_dt and window_key not in notified_destroyer:
                text = f"💀 **{DISPLAY_NAME.get(boss_norm,boss_norm.title())}** is active now ({start_t.strftime('%I:%M %p')}-{end_t.strftime('%I:%M %p')})."
                await send_to_channels(text)
                notified_destroyer.add(window_key)

# -----------------------
# Background cleanup loop (1 minute)
# -----------------------
@tasks.loop(minutes=1)
async def cleanup_loop():
    now = now_ph()
    expired = [mid for mid, (_, expiry) in message_cleanup.items() if expiry <= now]
    for mid in expired:
        ch_id, _ = message_cleanup.get(mid, (None, None))
        if ch_id:
            ch = bot.get_channel(ch_id)
            if ch:
                try:
                    m = await ch.fetch_message(mid)
                    await m.delete()
                    print(f"🗑 Deleted cleaned-up message {mid} in channel {ch_id}")
                except Exception:
                    pass
        message_cleanup.pop(mid, None)

# -----------------------
# On ready: sync commands & start loops
# -----------------------
@bot.event
async def on_ready():
    try:
        if GUILD_ID:
            await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
            print(f"🔗 Synced slash commands to guild {GUILD_ID}")
        else:
            await bot.tree.sync()
            print("🔗 Synced global slash commands")
    except Exception as e:
        print("⚠️ Slash sync failed:", e)

    if not reminders_loop.is_running():
        reminders_loop.start()
    if not cleanup_loop.is_running():
        cleanup_loop.start()
    print(f"✅ Logged in as {bot.user} (UTC+8 used)")

# -----------------------
# Run
# -----------------------
bot.run(TOKEN)
