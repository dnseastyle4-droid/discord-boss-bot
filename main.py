# main.py
import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, time
import pytz
from keep_alive import keep_alive

# -----------------------------
# Environment Variables
# -----------------------------
TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("Enemies"))
CHANNEL_ID = int(os.getenv("sdn"))

if not TOKEN or not GUILD_ID or not CHANNEL_ID:
    raise RuntimeError("Environment variables TOKEN, Enemies, or sdn are missing!")

# -----------------------------
# Timezone
# -----------------------------
UTC8 = pytz.timezone("Asia/Manila")

# -----------------------------
# Bot Initialization
# -----------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# -----------------------------
# Boss Configurations
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

DESTROYER_BOSS = "Destroyer"
DESTROYER_TIMES = [(time(11, 0), time(12, 0)), (time(20, 0), time(21, 0))]  # UTC+8

# -----------------------------
# Timers
# -----------------------------
world_timers = {}     # {boss_name: datetime}
unique_timers = {}    # {monster_name: datetime}
destroyer_sent = False

# -----------------------------
# Keep Alive
# -----------------------------
keep_alive()

# -----------------------------
# Bot Ready
# -----------------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    guild = discord.Object(id=GUILD_ID)
    await tree.sync(guild=guild)
    print(f"🔗 Synced slash commands to guild {GUILD_ID}")
    if not timer_loop.is_running():
        timer_loop.start()

# -----------------------------
# Helpers
# -----------------------------
def format_time(dt):
    return dt.astimezone(UTC8).strftime("%I:%M %p")

async def get_channel():
    return bot.get_channel(CHANNEL_ID)

def is_world_boss(name):
    return name in WORLD_BOSSES

def is_unique(name):
    return name in UNIQUE_MONSTERS

# -----------------------------
# Autocomplete
# -----------------------------
async def boss_autocomplete(interaction: discord.Interaction, current: str):
    options = list(WORLD_BOSSES.keys()) + list(UNIQUE_MONSTERS.keys()) + [DESTROYER_BOSS]
    return [
        app_commands.Choice(name=b, value=b)
        for b in options if current.lower() in b.lower()
    ][:25]

# -----------------------------
# Slash Commands
# -----------------------------
@tree.command(name="ping", description="Check if the bot is awake")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong! 🏓 I'm awake and ready!")

@tree.command(name="add", description="Add a boss/monster timer")
@app_commands.describe(name="Boss or monster name")
@app_commands.autocomplete(name=boss_autocomplete)
async def add(interaction: discord.Interaction, name: str):
    now = datetime.now(UTC8)
    if is_world_boss(name):
        world_timers[name] = now + timedelta(hours=WORLD_BOSSES[name])
        await interaction.response.send_message(f"✅ {name} added! Respawn at {format_time(world_timers[name])}")
    elif is_unique(name):
        unique_timers[name] = now + timedelta(minutes=UNIQUE_MONSTERS[name])
        await interaction.response.send_message(f"✅ {name} added! Respawn at {format_time(unique_timers[name])}")
    elif name == DESTROYER_BOSS:
        await interaction.response.send_message(f"✅ {DESTROYER_BOSS} notifications enabled.")
    else:
        await interaction.response.send_message("❌ Boss/monster not found.")

@tree.command(name="remove", description="Remove a boss/monster timer")
@app_commands.describe(name="Boss or monster name")
@app_commands.autocomplete(name=boss_autocomplete)
async def remove(interaction: discord.Interaction, name: str):
    removed = False
    if name in world_timers:
        del world_timers[name]
        removed = True
    if name in unique_timers:
        del unique_timers[name]
        removed = True
    if removed:
        await interaction.response.send_message(f"✅ {name} timer removed.")
    else:
        await interaction.response.send_message(f"❌ No active timer for {name}.")

@tree.command(name="help", description="Instructions for using the bot")
async def help(interaction: discord.Interaction):
    msg = (
        "**Bot Commands**\n"
        "/ping - Check if the bot is awake\n"
        "/add <Boss/Monster> - Start timer\n"
        "   Examples:\n"
        "      /add Alarak\n"
        "      /add Venatus\n"
        "/remove <Boss/Monster> - Remove timer\n"
        "   Examples:\n"
        "      /remove Alarak\n"
        "      /remove Undomiel\n"
        "Destroyer notifications are automatic during 11AM-12PM and 8PM-9PM UTC+8."
    )
    await interaction.response.send_message(msg)

# -----------------------------
# Timer Loop (Single Notification)
# -----------------------------
@tasks.loop(minutes=1)
async def timer_loop():
    now = datetime.now(UTC8)
    channel = await get_channel()
    if not channel:
        return

    # World bosses
    for name, dt in list(world_timers.items()):
        if now >= dt - timedelta(minutes=2) and now < dt:
            await channel.send(f"⚔️ **{name}** will spawn in ~2 minutes!")
            del world_timers[name]  # notify once

    # Unique monsters
    for name, dt in list(unique_timers.items()):
        if now >= dt - timedelta(minutes=1) and now < dt:
            await channel.send(f"🔥 **{name}** will spawn in ~1 minute!")
            del unique_timers[name]  # notify once

    # Destroyer boss (constant during scheduled times)
    global destroyer_sent
    for start, end in DESTROYER_TIMES:
        if start <= now.time() <= end:
            if not destroyer_sent:
                await channel.send(f"💀 **{DESTROYER_BOSS}** is active! Prepare!")
                destroyer_sent = True
        else:
            destroyer_sent = False

# -----------------------------
# Run Bot
# -----------------------------
bot.run(TOKEN)
