import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta

# -------- Intents --------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True  # only needed if you check members

bot = commands.Bot(command_prefix="/", intents=intents)

# -------- Config --------
CHANNEL_IDS = [int(cid) for cid in os.getenv("CHANNELS", "").split(",") if cid]  
# Example: set CHANNELS="123456789012345678,987654321098765432" in Render

DESTROYER_BOSSES = {"Ratan", "Parto", "Nedra"}
unique_bosses = {
    "Blood Mother", "Decoy", "Ghost Webber", "Shadow Webber",
    "Escort Leader Maximus", "Fortuneteller Ariel", "Priest Petroca",
    "Sylandra", "Halfmoon Stone Turtle", "Cobolt Blitz Captain",
    "Black Wings", "Forgotten Olive", "Deadman's Grow", "Cassandra",
    "Mutated Scorpion", "Berserk Higher Harpy", "Red Lizardman Patrol Captain",
    "Lyrian", "Durian", "Infected Kukri", "Straggler Brown", "Veridon",
    "Shaug Blitz Captain", "Shaug High-Ranking Wizard", "Shaug Patrol Captain",
    "Elder Lich", "Catena's Eye", "Elder Scorpius", "Catena's Servant",
    "Catena's Cry", "Catena's Ego", "Catena's Rage", "Catena's Sorrow",
}

scheduled_bosses = {
    "Clemantis": [("Monday", "11:30"), ("Thursday", "19:00")],
    "Saphirus": [("Sunday", "17:00"), ("Tuesday", "11:30")],
    "Neutro": [("Tuesday", "19:00"), ("Thursday", "11:30")],
    "Thymele": [("Monday", "19:00"), ("Wednesday", "11:30")],
    "Milavy": [("Saturday", "15:00")],
    "Ringor": [("Saturday", "17:00")],
    "Roderick": [("Friday", "19:00")],
    "Auraq": [("Sunday", "21:00"), ("Wednesday", "21:00")],
    "Chailflock": [("Saturday", "22:00")],
}

pending_bosses = {}  # {boss: datetime}

# -------- Commands --------
@bot.command(name="guide")
async def guide(ctx):
    """Show all available commands."""
    msg = (
        "**Boss Bot Guide**\n\n"
        "🔹 `/add <boss>` → Track a boss respawn (case-insensitive).\n"
        "🔹 `/status` → Show pending bosses.\n"
        "🔹 `/guide` → Show this help message.\n\n"
        "🕒 Unique bosses respawn every **15 minutes**.\n"
        "📅 Some bosses have fixed schedules.\n"
        "💥 Destroyer bosses (Ratan, Parto, Nedra) are notified only once."
    )
    await ctx.send(msg)


@bot.command(name="add")
async def add(ctx, *, boss: str):
    boss = boss.strip().title()  # case-insensitive
    now = datetime.utcnow() + timedelta(hours=8)

    # Destroyers → notify once
    if boss in DESTROYER_BOSSES:
        if boss in pending_bosses:
            return
        respawn_time = now + timedelta(minutes=15)
        pending_bosses[boss] = respawn_time
        for cid in CHANNEL_IDS:
            channel = bot.get_channel(cid)
            if channel:
                await channel.send(f"💀 **{boss}** (Destroyer) has spawned! Respawn in 15 mins.")
        return

    # Unique bosses → 15 min respawn
    if boss in unique_bosses:
        respawn_time = now + timedelta(minutes=15)
        pending_bosses[boss] = respawn_time
        for cid in CHANNEL_IDS:
            channel = bot.get_channel(cid)
            if channel:
                await channel.send(f"⚔️ **{boss}** added! Respawn in 15 mins.")
        return

    # Scheduled bosses
    if boss in scheduled_bosses:
        for cid in CHANNEL_IDS:
            channel = bot.get_channel(cid)
            if channel:
                await channel.send(f"📅 **{boss}** is a scheduled boss. Use `/status` to see times.")
        return


@bot.command(name="status")
async def status(ctx):
    """Show pending bosses."""
    now = datetime.utcnow() + timedelta(hours=8)
    active = [f"{boss} → respawns at {time.strftime('%H:%M')}" 
              for boss, time in pending_bosses.items() if time > now]

    # Scheduled bosses (only 2–3 hours near)
    today = now.strftime("%A")
    current_time = now.strftime("%H:%M")
    nearby = []
    for boss, times in scheduled_bosses.items():
        for day, t in times:
            if day == today:
                boss_time = datetime.strptime(t, "%H:%M").time()
                check_time = now.replace(hour=boss_time.hour, minute=boss_time.minute, second=0)
                if timedelta(hours=-2) <= (check_time - now) <= timedelta(hours=3):
                    nearby.append(f"{boss} → {day} {t}")

    msg = "**📊 Pending Bosses:**\n"
    msg += "\n".join(active) if active else "None right now."
    msg += "\n\n**📅 Nearby Scheduled Bosses (2–3 hrs):**\n"
    msg += "\n".join(nearby) if nearby else "None upcoming."
    await ctx.send(msg)


# -------- Background Task --------
@tasks.loop(seconds=60)
async def check_respawns():
    now = datetime.utcnow() + timedelta(hours=8)
    expired = []
    for boss, respawn_time in pending_bosses.items():
        if now >= respawn_time:
            for cid in CHANNEL_IDS:
                channel = bot.get_channel(cid)
                if channel:
                    await channel.send(f"🔔 **{boss}** has respawned!")
            expired.append(boss)
    for boss in expired:
        del pending_bosses[boss]


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    check_respawns.start()


# -------- Run --------
bot.run(os.getenv("DISCORD_TOKEN"))
