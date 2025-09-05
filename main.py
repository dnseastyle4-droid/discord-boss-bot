# main.py — full corrected slash-command bot (includes Alarak, Black Wedge, Dark Apparition, Thardus variants, etc.)
import os
import re
import threading
import asyncio
from datetime import datetime, timedelta, time, timezone
from typing import List, Dict

import discord
from discord import app_commands
from discord.ext import commands, tasks
from flask import Flask

# -------------------------
# Environment / basic config
# -------------------------
TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
CHANNELS_ENV = os.getenv("CHANNELS") or os.getenv("CHANNELS_LIST") or ""
CHANNEL_IDS: List[int] = [int(x) for x in CHANNELS_ENV.split(",") if x.strip().isdigit()]
GUILD_RAW = os.getenv("GUILD_ID") or os.getenv("Enemies")
GUILD_ID = int(GUILD_RAW) if GUILD_RAW and GUILD_RAW.isdigit() else None

if not TOKEN:
    raise RuntimeError("Set DISCORD_TOKEN or TOKEN environment variable.")
if not CHANNEL_IDS:
    raise RuntimeError("Set CHANNELS env var to a comma-separated list of channel IDs (CHANNELS).")

# timezone (UTC+8)
TZ = timezone(timedelta(hours=8))

# -------------------------
# Flask keep-alive (so hosts see an open port)
# -------------------------
app = Flask("keepalive")

@app.route("/")
def home():
    return "Boss bot alive!"

def background_flask():
    # run Flask in a background thread (port 8080)
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=background_flask, daemon=True).start()

# -------------------------
# Bot & intents (minimal)
# -------------------------
intents = discord.Intents.default()
intents.guilds = True  # needed for slash commands and guild info
# Avoid message_content/members privileged intents unless required
bot = commands.Bot(command_prefix="!", intents=intents)
tree = app_commands.CommandTree(bot)

# -------------------------
# Raw lists (original display names)
# -------------------------
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

# Unique monsters (all are 15-min respawn when added)
UNIQUE_RAW = [
    # earlier sets + additions (including Alarak, Black Wedge, Thardus variants, Dark Apparition, Suspicious Wizard, etc.)
    "Alarak", "Black Wedge", "Outlaw Kaiser", "Screaming Wings", "Suspicious Wizard",
    "Dark Apparition", "Brutal Butcher", "Corrupted Shellbug", "Secret Creation",
    "Magic Puppet", "Wizard's Puppet", "Lamia Shaman", "Angusto",
    "Berserk Thardus", "Ancient Thardus", "Charging Thardus",
    "Desert Golem", "Ancient Turtle", "Protector of the Ruins", "Black Hand",
    "Ancient Protector", "Intikam", "Desert Protector",

    # the long list you gave later
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

# -------------------------
# Normalization helpers & maps
# -------------------------
def normalize(s: str) -> str:
    s = s or ""
    s = s.lower()
    # remove punctuation except spaces and keep alphanumerics
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

# Build normalized dictionaries and display map
DISPLAY_NAME: Dict[str, str] = {}
WORLD_BOSSES: Dict[str, int] = {}
for k, hrs in WORLD_BOSSES_RAW.items():
    nk = normalize(k)
    WORLD_BOSSES[nk] = hrs
    DISPLAY_NAME[nk] = k

SCHEDULED_BOSSES: Dict[str, List[tuple]] = {}
for k, times in SCHEDULED_BOSSES_RAW.items():
    nk = normalize(k)
    SCHEDULED_BOSSES[nk] = times
    DISPLAY_NAME[nk] = k

UNIQUE_MONSTERS = set()
for k in UNIQUE_RAW:
    nk = normalize(k)
    UNIQUE_MONSTERS.add(nk)
    DISPLAY_NAME[nk] = k

DESTROYER_BOSSES = set(normalize(x) for x in DESTROYER_RAW)
for x in DESTROYER_RAW:
    DISPLAY_NAME[normalize(x)] = x

# Build autocomplete source list (normalized keys)
ALL_KEYS = list(WORLD_BOSSES.keys()) + list(UNIQUE_MONSTERS) + list(SCHEDULED_BOSSES.keys()) + list(DESTROYER_BOSSES)

# -------------------------
# Runtime storage
# -------------------------
# pending: normalized_name -> {"display": str, "respawn": aware-datetime, "kind": "world"|"unique"}
pending: Dict[str, Dict] = {}
notified_scheduled = set()
notified_destroyer = set()

# -------------------------
# Time helpers
# -------------------------
def now_ph() -> datetime:
    return datetime.now(timezone.utc).astimezone(TZ)

def make_respawn_hours(hours: int) -> datetime:
    return now_ph() + timedelta(hours=hours)

def make_respawn_minutes(minutes: int) -> datetime:
    return now_ph() + timedelta(minutes=minutes)

# -------------------------
# Send util
# -------------------------
async def send_to_channels(text: str):
    for cid in CHANNEL_IDS:
        ch = bot.get_channel(cid)
        if ch:
            try:
                await ch.send(text)
            except Exception:
                # ignore per-channel failures
                pass

# -------------------------
# Autocomplete (async)
# -------------------------
async def name_autocomplete(interaction: discord.Interaction, current: str):
    cur = (current or "").lower()
    choices = []
    for k in ALL_KEYS:
        disp = DISPLAY_NAME.get(k, k.title())
        if cur in disp.lower() or cur in k:
            choices.append(app_commands.Choice(name=disp, value=k))
            if len(choices) >= 25:
                break
    return choices

# -------------------------
# Slash commands
# -------------------------
@tree.command(name="guide", description="Show usage examples")
async def guide(interaction: discord.Interaction):
    text = (
        "**Boss Bot Guide**\n\n"
        "`/add <name>` — add a world boss or unique (case-insensitive).\n"
        "`/remove <name>` — remove a pending timer you added.\n"
        "`/status` — show pending added bosses and scheduled ones within 3 hrs.\n\n"
        "Examples:\n"
        "`/add Alarak` — adds unique (15m)\n"
        "`/add Venatus` — adds world boss (10h)\n\n"
        "Destroyers (Ratan/Parto/Nedra) and scheduled bosses are automatic."
    )
    await interaction.response.send_message(text, ephemeral=True)

@tree.command(name="add", description="Add a boss or unique monster timer")
@app_commands.describe(name="Boss or monster name")
@app_commands.autocomplete(name=name_autocomplete)
async def add_cmd(interaction: discord.Interaction, name: str):
    # 'name' value will be the normalized key when chosen via autocomplete,
    # or raw typed string if user typed manually. Normalize as needed.
    norm = name if name in ALL_KEYS else normalize(name)
    now = now_ph()

    # Destroyer = automatic only
    if norm in DESTROYER_BOSSES:
        await interaction.response.send_message(f"⚠️ {DISPLAY_NAME.get(norm, norm.title())} is a Destroyer — reminders run automatically.", ephemeral=True)
        return

    # Unique monsters (15 minutes)
    if norm in UNIQUE_MONSTERS:
        if norm in pending:
            await interaction.response.send_message(f"⚠️ {DISPLAY_NAME[norm]} is already pending.", ephemeral=True)
            return
        respawn = make_respawn_minutes(15)
        pending[norm] = {"display": DISPLAY_NAME[norm], "respawn": respawn, "kind": "unique"}
        await interaction.response.send_message(f"✅ {DISPLAY_NAME[norm]} added — respawn at {respawn.strftime('%I:%M %p')}.", ephemeral=True)
        return

    # World bosses (hours)
    if norm in WORLD_BOSSES:
        if norm in pending:
            await interaction.response.send_message(f"⚠️ {DISPLAY_NAME[norm]} is already pending.", ephemeral=True)
            return
        hours = WORLD_BOSSES[norm]
        respawn = make_respawn_hours(hours)
        pending[norm] = {"display": DISPLAY_NAME[norm], "respawn": respawn, "kind": "world"}
        await interaction.response.send_message(f"✅ {DISPLAY_NAME[norm]} added — respawn at {respawn.strftime('%I:%M %p')} (in {hours}h).", ephemeral=True)
        return

    # Scheduled bosses
    if norm in SCHEDULED_BOSSES:
        await interaction.response.send_message(f"ℹ️ {DISPLAY_NAME[norm]} is scheduled — it will be announced automatically when within ~3 hours.", ephemeral=True)
        return

    await interaction.response.send_message(f"❌ Unknown boss/monster `{name}` — try autocomplete or `/guide`.", ephemeral=True)

@tree.command(name="remove", description="Remove a pending boss/unique timer")
@app_commands.describe(name="Boss or monster name")
@app_commands.autocomplete(name=name_autocomplete)
async def remove_cmd(interaction: discord.Interaction, name: str):
    norm = name if name in ALL_KEYS else normalize(name)
    if norm in pending:
        pending.pop(norm, None)
        await interaction.response.send_message(f"✅ Removed {DISPLAY_NAME.get(norm, norm.title())} from pending.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ {DISPLAY_NAME.get(norm, norm.title())} is not in pending list.", ephemeral=True)

@tree.command(name="status", description="Show pending bosses and scheduled ones within 3 hours")
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

    # Scheduled within 3 hours
    nearby = []
    weekday = now.strftime("%A").lower()
    for boss_key, scheds in SCHEDULED_BOSSES.items():
        for day, hhmm in scheds:
            if day == weekday:
                h, m = map(int, hhmm.split(":"))
                event_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                delta_h = (event_dt - now).total_seconds() / 3600
                if 0 < delta_h <= 3:
                    nearby.append(f"- {DISPLAY_NAME.get(boss_key, boss_key.title())} at {hhmm} (in {delta_h:.1f} hr)")
    if nearby:
        lines.append("**Scheduled (within 3 hrs)**:")
        lines.extend(nearby)
    else:
        lines.append("**Scheduled (within 3 hrs)**: none")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)

# -------------------------
# Background reminders loop
# -------------------------
@tasks.loop(minutes=1)
async def reminders_loop():
    now = now_ph()

    # World bosses: notify ~2 minutes before, one-time, then remove
    for key, info in list(pending.items()):
        if info["kind"] == "world":
            resp = info["respawn"]
            if now >= resp - timedelta(minutes=2):
                await send_to_channels(f"⚔️ **{info['display']}** will spawn in ~2 minutes! Prepare!")
                pending.pop(key, None)

    # Unique monsters: notify ~1 minute before, one-time, then remove
    for key, info in list(pending.items()):
        if info["kind"] == "unique":
            resp = info["respawn"]
            if now >= resp - timedelta(minutes=1) and now < resp:
                await send_to_channels(f"🔥 **{info['display']}** will spawn in ~1 minute! Get ready!")
            if now >= resp:
                # expire
                pending.pop(key, None)

    # Scheduled bosses: notify once when within 3 hours
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
                await send_to_channels(f"📢 Scheduled Boss **{DISPLAY_NAME.get(boss_key,boss_key.title())}** is coming at {hhmm} (in {delta_h:.1f} hr).")
                notified_scheduled.add(event_key)

    # Destroyer windows: notify once per window per day
    windows = [(time(11, 0), time(12, 0)), (time(20, 0), time(21, 0))]
    for boss_norm in DESTROYER_BOSSES:
        for start_t, end_t in windows:
            start_dt = now.replace(hour=start_t.hour, minute=start_t.minute, second=0, microsecond=0)
            end_dt = now.replace(hour=end_t.hour, minute=end_t.minute, second=0, microsecond=0)
            window_key = f"{boss_norm}-{start_dt.date()}-{start_t.strftime('%H%M')}"
            if start_dt <= now <= end_dt and window_key not in notified_destroyer:
                await send_to_channels(f"💀 **{DISPLAY_NAME.get(boss_norm,boss_norm.title())}** is active now ({start_t.strftime('%I:%M %p')}-{end_t.strftime('%I:%M %p')}).")
                notified_destroyer.add(window_key)

# -------------------------
# On ready: sync commands & start loop
# -------------------------
@bot.event
async def on_ready():
    try:
        if GUILD_ID:
            await tree.sync(guild=discord.Object(id=GUILD_ID))
            print(f"🔗 Synced slash commands to guild {GUILD_ID}")
        else:
            await tree.sync()
            print("🔗 Synced global slash commands")
    except Exception as e:
        print("⚠️ Slash command sync failed:", e)

    if not reminders_loop.is_running():
        reminders_loop.start()
    print(f"✅ Logged in as {bot.user} (UTC+8 timezone used)")

# -------------------------
# Run the bot
# -------------------------
bot.run(TOKEN)
