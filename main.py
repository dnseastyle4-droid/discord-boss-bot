# main.py — Final Boss Bot: full bosses, slash commands, autocomplete, keep-alive, unique auto-clean (30m)
import os
import re
import threading
from datetime import datetime, timedelta, timezone, time as dtime
from typing import List, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from flask import Flask

# -----------------------
# Environment / config
# -----------------------
TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
CHANNELS_ENV = os.getenv("CHANNELS", "")  # e.g. "123456789012345678,987654321098765432"
CHANNEL_IDS: List[int] = [int(x) for x in CHANNELS_ENV.split(",") if x.strip().isdigit()]
GUILD_RAW = os.getenv("GUILD_ID") or os.getenv("Enemies")
GUILD_ID = int(GUILD_RAW) if GUILD_RAW and GUILD_RAW.isdigit() else None

if not TOKEN:
    raise RuntimeError("Set DISCORD_TOKEN (or TOKEN) environment variable.")
if not CHANNEL_IDS:
    raise RuntimeError("Set CHANNELS environment variable (comma-separated channel IDs).")

# timezone (UTC+8)
TZ = timezone(timedelta(hours=8))

# -----------------------
# Flask keep-alive
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
bot = commands.Bot(command_prefix="!", intents=intents)
try:
    bot.remove_command("help")
except Exception:
    pass

# -----------------------
# Boss lists
# -----------------------
WORLD_BOSSES_RAW = {
    "Venatus": 10, "Viorent": 10, "Ego": 21, "Livera": 24, "Araneo": 24,
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
# Helpers
# -----------------------
def normalize(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.lower().replace("’","'")
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

WORLD_BOSSES: Dict[str,int] = {}
SCHEDULED_BOSSES: Dict[str,List[tuple]] = {}
UNIQUE_MONSTERS = set()
DESTROYER_BOSSES = set()
DISPLAY_NAME: Dict[str,str] = {}

for k,v in WORLD_BOSSES_RAW.items():
    nk = normalize(k)
    WORLD_BOSSES[nk] = v
    DISPLAY_NAME[nk] = k

for k,v in SCHEDULED_BOSSES_RAW.items():
    nk = normalize(k)
    SCHEDULED_BOSSES[nk] = v
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
pending: Dict[str, Dict] = {}
notified_scheduled = set()
notified_destroyer = set()
message_cleanup: Dict[int, tuple] = {}

def now_ph() -> datetime:
    return datetime.now(timezone.utc).astimezone(TZ)

def make_respawn_hours(h: int) -> datetime:
    return now_ph() + timedelta(hours=h)

def make_respawn_minutes(m: int) -> datetime:
    return now_ph() + timedelta(minutes=m)

async def send_to_channels(msg: str):
    for cid in CHANNEL_IDS:
        ch = bot.get_channel(cid)
        if ch:
            try: await ch.send(msg)
            except: pass

async def send_to_channels_return(msg: str):
    sent = []
    for cid in CHANNEL_IDS:
        ch = bot.get_channel(cid)
        if ch:
            try:
                m = await ch.send(msg)
                sent.append(m)
            except: pass
    return sent

async def name_autocomplete(interaction: discord.Interaction, current: str):
    cur = (current or "").lower()
    choices = []
    for k in ALL_KEYS:
        disp = DISPLAY_NAME.get(k,k.title())
        if cur in disp.lower() or cur in k:
            choices.append(app_commands.Choice(name=disp,value=disp))
            if len(choices) >= 25: break
    return choices

# -----------------------
# Slash commands
# -----------------------
@bot.tree.command(name="guide", description="Show quick usage & examples")
async def guide(interaction: discord.Interaction):
    text = (
        "**Boss Bot Guide**\n\n"
        "`/add <name>` — Add a boss or unique monster.\n"
        "`/remove <name>` — Remove a pending timer.\n"
        "`/status` — Show pending timers & scheduled bosses for today.\n"
        "Destroyers are automatic.\n"
    )
    await interaction.response.send_message(text)

@bot.tree.command(name="add", description="Add a world boss or unique monster timer")
@app_commands.describe(name="Boss or monster name")
@app_commands.autocomplete(name=name_autocomplete)
async def add_cmd(interaction: discord.Interaction, name: str):
    disp = name.strip()
    norm = None
    for k,v in DISPLAY_NAME.items():
        if v.lower() == disp.lower():
            norm = k
            break
    if not norm: norm = normalize(disp)
    now = now_ph()

    if norm in DESTROYER_BOSSES:
        await interaction.response.send_message(f"⚠️ {DISPLAY_NAME.get(norm,norm.title())} is a Destroyer — reminders are automatic.")
        return

    if norm in UNIQUE_MONSTERS:
        if norm in pending:
            await interaction.response.send_message(f"⚠️ {DISPLAY_NAME[norm]} is already pending.")
            return
        resp = make_respawn_minutes(15)
        pending[norm] = {"display":DISPLAY_NAME[norm],"respawn":resp,"kind":"unique"}
        await interaction.response.send_message(f"✅ {DISPLAY_NAME[norm]} added — respawn at {resp.strftime('%I:%M %p')} (in 15 min).")
        return

    if norm in WORLD_BOSSES:
        if norm in pending:
            await interaction.response.send_message(f"⚠️ {DISPLAY_NAME[norm]} is already pending.")
            return
        hours = WORLD_BOSSES[norm]
        resp = make_respawn_hours(hours)
        pending[norm] = {"display":DISPLAY_NAME[norm],"respawn":resp,"kind":"world"}
        await interaction.response.send_message(f"✅ {DISPLAY_NAME[norm]} added — respawn at {resp.strftime('%I:%M %p')} (in {hours}h).")
        return

    if norm in SCHEDULED_BOSSES:
        await interaction.response.send_message(f"ℹ️ {DISPLAY_NAME.get(norm,norm.title())} is scheduled — will be announced automatically.")
        return

    await interaction.response.send_message(f"❌ Unknown boss/monster: `{name}` — try autocomplete.")

@bot.tree.command(name="remove", description="Remove a world/unique timer you added")
@app_commands.describe(name="Boss or monster name")
@app_commands.autocomplete(name=name_autocomplete)
async def remove_cmd(interaction: discord.Interaction, name: str):
    disp = name.strip()
    norm = None
    for k,v in DISPLAY_NAME.items():
        if v.lower() == disp.lower(): norm = k; break
    if not norm: norm = normalize(disp)
    if norm in pending:
        pending.pop(norm,None)
        notified_scheduled.discard(norm)
        notified_destroyer.discard(norm)
        await interaction.response.send_message(f"✅ Removed {DISPLAY_NAME.get(norm,norm.title())} from pending.")
    else:
        await interaction.response.send_message(f"❌ {DISPLAY_NAME.get(norm,norm.title())} is not pending.")

@bot.tree.command(name="status", description="Show pending timers & scheduled bosses for today")
async def status_cmd(interaction: discord.Interaction):
    now = now_ph()
    lines = []

    # Pending added
    if pending:
        lines.append("**Pending (added)**:")
        for k, info in pending.items():
            resp = info["respawn"]
            mins = int((resp-now).total_seconds()//60)
            if mins>0:
                lines.append(f"- {info['display']} — in {mins} min (at {resp.strftime('%I:%M %p')})")
            else:
                lines.append(f"- {info['display']} — due now")
    else:
        lines.append("**Pending (added)**: none")

    # Scheduled bosses for today
    today_bosses = []
    weekday = now.strftime("%A").lower()
    for boss_key, scheds in SCHEDULED_BOSSES.items():
        for day, hhmm in scheds:
            if day != weekday: continue
            today_bosses.append(f"- {DISPLAY_NAME.get(boss_key,boss_key.title())} at {hhmm}")
    if today_bosses:
        lines.append("**Scheduled Bosses Today:**")
        lines.extend(today_bosses)
    else:
        lines.append("**Scheduled Bosses Today:** none")

    await interaction.response.send_message("\n".join(lines))

# -----------------------
# Background loops
# -----------------------
@tasks.loop(minutes=1)
async def reminders_loop():
    now = now_ph()
    # World bosses
    for key, info in list(pending.items()):
        if info["kind"]=="world":
            resp = info["respawn"]
            if now >= resp - timedelta(minutes=2):
                text = f"⚔️ **{info['display']}** will spawn in ~2 minutes!"
                await send_to_channels(text)
                pending.pop(key,None)
    # Unique
    for key, info in list(pending.items()):
        if info["kind"]=="unique":
            resp = info["respawn"]
            if now >= resp - timedelta(minutes=1) and now < resp:
                text = f"🔥 **{info['display']}** will spawn in ~1 minute!"
                messages = await send_to_channels_return(text)
                expiry = now + timedelta(minutes=30)
                for m in messages: message_cleanup[m.id]=(m.channel.id,expiry)
            if now >= resp: pending.pop(key,None)
    # Scheduled bosses auto
    weekday = now.strftime("%A").lower()
    for boss_key,scheds in SCHEDULED_BOSSES.items():
        for day, hhmm in scheds:
            if day != weekday: continue
            h,m = map(int,hhmm.split(":"))
            event_dt = now.replace(hour=h,minute=m,second=0,microsecond=0)
            delta_h = (event_dt-now).total_seconds()/3600
            event_key=f"{boss_key}-{event_dt.date()}-{hhmm}"
            if 0<delta_h<=3 and event_key not in notified_scheduled:
                text=f"📢 Scheduled Boss **{DISPLAY_NAME.get(boss_key,boss_key.title())}** is coming at {hhmm} (in {delta_h:.1f} hr)."
                await send_to_channels(text)
                notified_scheduled.add(event_key)
    # Destroyers
    windows = [(dtime(11,0),dtime(12,0)),(dtime(20,0),dtime(21,0))]
    for boss_norm in DESTROYER_BOSSES:
        for start_t,end_t in windows:
            start_dt = now.replace(hour=start_t.hour,minute=start_t.minute,second=0,microsecond=0)
            end_dt = now.replace(hour=end_t.hour,minute=end_t.minute,second=0,microsecond=0)
            window_key=f"{boss_norm}-{start_dt.date()}-{start_t.strftime('%H%M')}"
            if start_dt<=now<=end_dt and window_key not in notified_destroyer:
                text=f"💀 **{DISPLAY_NAME.get(boss_norm,boss_norm.title())}** is active now ({start_t.strftime('%I:%M %p')}-{end_t.strftime('%I:%M %p')})."
                await send_to_channels(text)
                notified_destroyer.add(window_key)

@tasks.loop(minutes=1)
async def cleanup_loop():
    now = now_ph()
    expired = [mid for mid,(_,expiry) in message_cleanup.items() if expiry<=now]
    for mid in expired:
        ch_id,_ = message_cleanup.get(mid,(None,None))
        if ch_id:
            ch = bot.get_channel(ch_id)
            if ch:
                try: m = await ch.fetch_message(mid); await m.delete()
                except: pass
        message_cleanup.pop(mid,None)

# -----------------------
# On ready
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
    if not reminders_loop.is_running(): reminders_loop.start()
    if not cleanup_loop.is_running(): cleanup_loop.start()
    print(f"✅ Logged in as {bot.user} (UTC+8)")

# -----------------------
# Run
# -----------------------
bot.run(TOKEN)
