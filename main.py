import os
import asyncio
from datetime import datetime, timedelta, UTC
import discord
from discord.ext import commands

# Read multiple channels from env
CHANNEL_IDS = [int(x) for x in os.getenv("CHANNELS", "").split(",") if x.strip()]
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# Boss respawn times (minutes) and schedules
boss_timers = {
    "alarak": 15, "general aquileus": 15, "venatus": 15, "viorent": 15,
    "supore": 62, "ego": 15, "asta": 62, "secreta": 62, "ordo": 62,
    "baron braudmore": 15, "gareth": 32, "shuliar": 35, "larba": 35,
    "undomiel": 15, "livera": 15, "araneo": 15, "lady dalia": 15,
    "catena": 35, "milavy": 37, "titore": 37, "ring or": 37, "chailflock": 37,
    "duplican": 48, "metus": 48, "wannitas": 48,
}

scheduled_bosses = {
    "clemantis": [("Monday", "11:30"), ("Thursday", "19:00")],
    "saphirus": [("Sunday", "17:00"), ("Tuesday", "11:30")],
    "neutro": [("Tuesday", "19:00"), ("Thursday", "11:30")],
    "thymele": [("Monday", "19:00"), ("Wednesday", "11:30")],
    "milavy": [("Saturday", "15:00")],
    "ringor": [("Saturday", "17:00")],
    "roderick": [("Friday", "19:00")],
    "auraq": [("Sunday", "21:00"), ("Wednesday", "21:00")],
    "chailflock": [("Saturday", "22:00")],
}

destroyer_bosses = {"ratan", "parto", "nedra"}

unique_monsters = {
    "blood mother", "decoy", "ghost webber", "shadow webber",
    "escort leader maximus", "fortuneteller ariel", "priest petroca",
    "sylandra", "halfmoon stone turtle", "cobolt blitz captain",
    "black wings", "forgotten olive", "deadman's grow", "cassandra", "mutated scorpion",
    "berserk higher harpy", "red lizardman patrol captain", "lyrian", "durian",
    "infected kukri", "straggler brown", "veridon", "shaug blitz captain",
    "shaug high-ranking wizard", "shaug patrol captain", "elder lich",
    "catena's eye", "elder scorpius", "catena's servant", "catena's cry",
    "catena's ego", "catena's rage", "catena's sorrow"
}

# Track active bosses and notifications
active_bosses = {}
notified_bosses = set()

# ------------------- HELP -------------------
@bot.command()
async def help(ctx):
    msg = (
        "**Boss Bot Commands**\n"
        "`/add <boss>` – Start a timer for a boss (case insensitive)\n"
        "`/status` – Show pending bosses\n\n"
        "**Notes:**\n"
        "- Each boss notifies **once only** per spawn.\n"
        "- Destroyer bosses (Ratan, Parto, Nedra) also notify only once.\n"
        "- Scheduled bosses (e.g., Clemantis, Milavy) trigger automatically near spawn.\n"
        "- Unique monsters have **15m respawn timers**."
    )
    await ctx.send(msg)

# ------------------- ADD -------------------
@bot.command()
async def add(ctx, *, boss_name: str):
    boss_name = boss_name.lower().strip()

    # Prevent duplicates
    if boss_name in notified_bosses:
        await ctx.send(f"⚠️ {boss_name.title()} is already being tracked.")
        return

    now = datetime.now(UTC) + timedelta(hours=8)

    if boss_name in boss_timers or boss_name in unique_monsters:
        respawn_time = boss_timers.get(boss_name, 15)
        notify_time = now + timedelta(minutes=respawn_time)
        active_bosses[boss_name] = notify_time
        notified_bosses.add(boss_name)
        await ctx.send(f"✅ {boss_name.title()} added. Respawn in {respawn_time} minutes.")
    elif boss_name in destroyer_bosses:
        active_bosses[boss_name] = now + timedelta(minutes=15)
        notified_bosses.add(boss_name)
        await ctx.send(f"💀 Destroyer {boss_name.title()} tracked (once-only).")
    else:
        await ctx.send(f"❌ Unknown boss: {boss_name}")

# ------------------- STATUS -------------------
@bot.command()
async def status(ctx):
    if not active_bosses:
        await ctx.send("📭 No pending bosses right now.")
        return

    msg = "**Pending Bosses:**\n"
    for boss, time in active_bosses.items():
        msg += f"- {boss.title()} at {time.strftime('%H:%M:%S')}\n"
    await ctx.send(msg)

# ------------------- REMINDER LOOP -------------------
async def reminder_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now(UTC) + timedelta(hours=8)

        expired = []
        for boss, time in active_bosses.items():
            if now >= time:
                for cid in CHANNEL_IDS:
                    channel = bot.get_channel(cid)
                    if channel:
                        await channel.send(f"⏰ {boss.title()} has respawned!")
                expired.append(boss)

        for boss in expired:
            del active_bosses[boss]
            notified_bosses.discard(boss)

        await asyncio.sleep(30)

bot.loop.create_task(reminder_loop())

# ------------------- BOT START -------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

bot.run(TOKEN)
