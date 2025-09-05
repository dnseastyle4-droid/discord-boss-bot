import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import pytz

# Intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

# Bot setup
bot = commands.Bot(command_prefix="/", intents=intents)

# Boss respawn times (minutes)
BOSS_RESPAWN = {
    # Normal bosses
    "supore": 62, "asta": 62, "secreta": 62, "ordo": 62,
    "gareth": 32, "shuliar": 35, "larba": 35, "catena": 35,
    "titore": 37, "duplican": 48, "metus": 48, "wannitas": 48,

    # Unique monsters (always 15 mins)
    "blood mother": 15, "decoy": 15, "ghost webber": 15, "shadow webber": 15,
    "escort leader maximus": 15, "fortuneteller ariel": 15, "priest petroca": 15,
    "sylandra": 15, "halfmoon stone turtle": 15, "cobolt blitz captain": 15,
    "black wings": 15, "forgotten olive": 15, "deadman's grow": 15,
    "cassandra": 15, "mutated scorpion": 15, "berserk higher harpy": 15,
    "red lizardman patrol captain": 15, "lyrian": 15, "durian": 15,
    "infected kukri": 15, "straggler brown": 15, "veridon": 15,
    "shaug blitz captain": 15, "shaug high-ranking wizard": 15,
    "shaug patrol captain": 15, "elder lich": 15, "catena's eye": 15,
    "elder scorpius": 15, "catena's servant": 15, "catena's cry": 15,
    "catena's ego": 15, "catena's rage": 15, "catena's sorrow": 15,
}

# Destroyer bosses (no respawn timer, notify once only)
DESTROYERS = {"ratan", "parto", "nedra"}

# Scheduled bosses (weekly fixed spawns)
SCHEDULED_BOSSES = {
    "clemantis": [("monday", "11:30"), ("thursday", "19:00")],
    "saphirus": [("sunday", "17:00"), ("tuesday", "11:30")],
    "neutro": [("tuesday", "19:00"), ("thursday", "11:30")],
    "thymele": [("monday", "19:00"), ("wednesday", "11:30")],
    "milavy": [("saturday", "15:00")],
    "ringor": [("saturday", "17:00")],
    "roderick": [("friday", "19:00")],
    "auraq": [("sunday", "21:00"), ("wednesday", "21:00")],
    "chailflock": [("saturday", "22:00")],
}

# Channel IDs (supports multiple)
CHANNEL_IDS = [int(cid) for cid in os.getenv("CHANNELS", "").split(",") if cid]

# Track active timers
active_bosses = {}

# Convert UTC to Manila time
PH_TZ = pytz.timezone("Asia/Manila")


def now_ph():
    return datetime.now(PH_TZ)


async def notify_channels(message: str):
    """Send a message to all configured channels."""
    for cid in CHANNEL_IDS:
        channel = bot.get_channel(cid)
        if channel:
            await channel.send(message)


@bot.command(name="add")
async def add_boss(ctx, *, boss_name: str):
    boss = boss_name.lower().strip()
    now = now_ph()

    if boss in DESTROYERS:
        if boss in active_bosses:
            await ctx.send(f"⚠️ {boss.title()} is already tracked.")
        else:
            active_bosses[boss] = None  # no respawn, just mark as notified
            await notify_channels(f"💀 Destroyer Boss **{boss.title()}** has spawned!")
        return

    if boss in BOSS_RESPAWN:
        if boss in active_bosses:
            await ctx.send(f"⚠️ {boss.title()} is already being tracked.")
        else:
            respawn_time = now + timedelta(minutes=BOSS_RESPAWN[boss])
            active_bosses[boss] = respawn_time
            await notify_channels(
                f"⚔️ Boss **{boss.title()}** added! Respawn in {BOSS_RESPAWN[boss]} mins "
                f"at {respawn_time.strftime('%H:%M')}."
            )
        return

    if boss in SCHEDULED_BOSSES:
        await ctx.send(f"📅 {boss.title()} is a scheduled boss. It cannot be manually added.")
        return

    await ctx.send(f"❌ Unknown boss: `{boss_name}`")


@bot.command(name="status")
async def status(ctx):
    if not active_bosses:
        await ctx.send("✅ No pending bosses right now.")
        return

    lines = []
    now = now_ph()
    for boss, respawn_time in active_bosses.items():
        if boss in DESTROYERS:
            lines.append(f"💀 {boss.title()} (Destroyer, notified once)")
        elif respawn_time:
            remaining = int((respawn_time - now).total_seconds() // 60)
            if remaining > 0:
                lines.append(f"⚔️ {boss.title()} → {remaining} mins left (until {respawn_time.strftime('%H:%M')})")
            else:
                lines.append(f"⚔️ {boss.title()} → Respawned!")
    if lines:
        await ctx.send("📋 **Pending Bosses:**\n" + "\n".join(lines))


@bot.command(name="guide")
async def guide(ctx):
    msg = (
        "**🛠️ Bot Guide**\n"
        "`/add <boss>` → Track a boss (case-insensitive)\n"
        "`/status` → Show all pending bosses\n"
        "Destroyer bosses (Ratan, Parto, Nedra) only notify once.\n"
        "Unique monsters respawn every 15 mins.\n"
        "Scheduled bosses are announced automatically near their times.\n"
    )
    await ctx.send(msg)


@tasks.loop(minutes=1)
async def scheduled_check():
    now = now_ph()
    weekday = now.strftime("%A").lower()
    current_time = now.strftime("%H:%M")

    for boss, schedules in SCHEDULED_BOSSES.items():
        for day, sched_time in schedules:
            if weekday == day and current_time == sched_time:
                await notify_channels(f"📅 Scheduled Boss **{boss.title()}** is spawning now!")


@tasks.loop(minutes=1)
async def respawn_check():
    now = now_ph()
    expired = []
    for boss, respawn_time in active_bosses.items():
        if respawn_time and now >= respawn_time:
            await notify_channels(f"⚔️ Boss **{boss.title()}** has respawned!")
            expired.append(boss)
    for boss in expired:
        del active_bosses[boss]


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    scheduled_check.start()
    respawn_check.start()


# Run bot
bot.run(os.getenv("DISCORD_TOKEN"))
