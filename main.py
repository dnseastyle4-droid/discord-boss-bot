# main.py
import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, time
from keep_alive import keep_alive

# -----------------------------
# Environment Variables
# -----------------------------
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL"))  # Channel for reminders

# -----------------------------
# Bot Initialization
# -----------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# -----------------------------
# Boss Categories
# -----------------------------
WORLD_BOSSES = {
    "Venatus": 10,
    "Viorent": 10,
    "Ego": 21,
    "Livera": 24,
    "Araneo": 21,
    "Undomiel": 24,
    "Lady Dalia": 18,
    "General Aquleus": 29,
    "Amentis": 29,
    "Baron Braudmore": 32
}

UNIQUE_MONSTERS = {
    "Outlaw Kaiser": 15,
    "Screaming Wings": 15,
    "Suspicious Wizard": 15,
    "Dark Apparition": 15,
    "Brutal Butcher": 15,
    "Corrupted Shellbug": 15,
    "Secret Creation": 15,
    "Magic Puppet": 15,
    "Wizard's Puppet": 15,
    "Lamia Shaman": 15,
    "Angusto": 15,
    "Berserk Thardus": 15,
    "Ancient Thardus": 15,
    "Charging Thardus": 15,
    "Desert Golem": 15,
    "Alarak": 15,
    "Ancient Turtle": 15,
    "Protector of the Ruins": 15,
    "Black Hand": 15,
    "Ancient Protector": 15,
    "Black Wedge": 15,
    "Intikam": 15,
    "Desert Protector": 15
}

DESTROYER_BOSSES = ["Ratan", "Parto", "Nedra"]

# -----------------------------
# Timer Storage
# -----------------------------
boss_timers = {}  # {name_lower: {"display": str, "respawn": datetime}}
unique_timers = {}  # {name_lower: {"display": str, "respawn": datetime}}
destroyer_timers = {}  # fixed schedule handled separately

# -----------------------------
# Helper Functions
# -----------------------------
def utc8_now():
    return datetime.utcnow() + timedelta(hours=8)

def format_time(dt):
    return dt.strftime("%I:%M %p")  # 12-hour format

def normalize_name(name: str):
    return name.strip().lower()

# -----------------------------
# Keep Alive
# -----------------------------
keep_alive()

# -----------------------------
# Bot Ready Event
# -----------------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    if not check_timers.is_running():
        check_timers.start()

# -----------------------------
# Add Command
# -----------------------------
@bot.tree.command(name="add", description="Add a boss or unique monster timer")
@discord.app_commands.describe(name="Boss or monster name")
async def add(interaction: discord.Interaction, name: str):
    name_key = normalize_name(name)
    now = utc8_now()

    if name_key in [normalize_name(b) for b in WORLD_BOSSES]:
        respawn = now + timedelta(hours=WORLD_BOSSES[next(b for b in WORLD_BOSSES if normalize_name(b) == name_key)])
        boss_timers[name_key] = {"display": next(b for b in WORLD_BOSSES if normalize_name(b) == name_key), "respawn": respawn}
        await interaction.response.send_message(f"✅ **{boss_timers[name_key]['display']}** added! Spawns at {format_time(respawn)}")
    elif name_key in [normalize_name(u) for u in UNIQUE_MONSTERS]:
        respawn = now + timedelta(minutes=UNIQUE_MONSTERS[next(u for u in UNIQUE_MONSTERS if normalize_name(u) == name_key)])
        unique_timers[name_key] = {"display": next(u for u in UNIQUE_MONSTERS if normalize_name(u) == name_key), "respawn": respawn}
        await interaction.response.send_message(f"🔥 **{unique_timers[name_key]['display']}** added! Spawns at {format_time(respawn)}")
    else:
        await interaction.response.send_message("❌ Unknown boss/monster name!")

# -----------------------------
# Remove Command
# -----------------------------
@bot.tree.command(name="remove", description="Remove a boss or unique monster timer")
@discord.app_commands.describe(name="Boss or monster name")
async def remove(interaction: discord.Interaction, name: str):
    name_key = normalize_name(name)
    removed = False
    for d in [boss_timers, unique_timers]:
        if name_key in d:
            removed = True
            display = d[name_key]["display"]
            del d[name_key]
            await interaction.response.send_message(f"🗑️ **{display}** removed!")
            break
    if not removed:
        await interaction.response.send_message("❌ Boss/monster not found in active timers!")

# -----------------------------
# Status Command
# -----------------------------
@bot.tree.command(name="status", description="See all pending boss/unique timers")
async def status(interaction: discord.Interaction):
    now = utc8_now()
    msgs = []

    if boss_timers:
        msgs.append("**World Bosses:**")
        for info in boss_timers.values():
            remaining = info["respawn"] - now
            mins = int(remaining.total_seconds() / 60)
            msgs.append(f"{info['display']} - spawns in {mins} min")
    if unique_timers:
        msgs.append("**Unique Monsters:**")
        for info in unique_timers.values():
            remaining = info["respawn"] - now
            mins = int(remaining.total_seconds() / 60)
            msgs.append(f"{info['display']} - spawns in {mins} min")
    if not msgs:
        msgs = ["No active timers!"]

    await interaction.response.send_message("\n".join(msgs))

# -----------------------------
# Help Command
# -----------------------------
@bot.tree.command(name="help", description="Show how to use the bot")
async def help_cmd(interaction: discord.Interaction):
    msg = """
**Boss Bot Commands**
/add <name> - Add a world boss or unique monster timer (case-insensitive)
/remove <name> - Remove a timer
/status - Show all pending timers
/ping - Check if bot is alive

**Examples**
/add Alarak
/add Undomiel
/remove Alarak
/status
"""
    await interaction.response.send_message(msg)

# -----------------------------
# Ping Command
# -----------------------------
@bot.tree.command(name="ping", description="Check if the bot is alive")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong! Bot is awake.")

# -----------------------------
# Background Task: 1-min checks
# -----------------------------
@tasks.loop(minutes=1)
async def check_timers():
    now = utc8_now()
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("❌ Reminder channel not found.")
        return

    # World Bosses reminders (2 min before)
    for key, info in list(boss_timers.items()):
        if now >= info["respawn"] - timedelta(minutes=2):
            await channel.send(f"⚔️ **{info['display']}** will spawn in ~2 minutes!")
            del boss_timers[key]

    # Unique monsters reminders (1 min before)
    for key, info in list(unique_timers.items()):
        if now >= info["respawn"] - timedelta(minutes=1):
            await channel.send(f"🔥 **{info['display']}** will spawn in ~1 minute!")
            del unique_timers[key]

    # Destroyer bosses reminders (fixed schedule)
    for name in DESTROYER_BOSSES:
        # 11AM-12PM and 8PM-9PM UTC+8
        hr = now.hour
        if (hr == 11 or hr == 20):
            await channel.send(f"💀 **{name}** is active now!")

# -----------------------------
# Run the Bot
# -----------------------------
bot.run(TOKEN)
