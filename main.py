import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import asyncio
from keep_alive import keep_alive

# -----------------------------
# Environment Variables
# -----------------------------
TOKEN = os.getenv("DISCORD_TOKEN")      # Set this in Render secret
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

# -----------------------------
# Bot Initialization
# -----------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# -----------------------------
# Boss Configuration
# -----------------------------
BOSSES = {
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

boss_timers = {}  # {boss_name: respawn_datetime}

# -----------------------------
# Unique Monsters
# -----------------------------
UNIQUE_MONSTERS = {
    "Alarak": 15,
    "Black Wedge": 15,
}

unique_timers = {}  # {monster_name: next_spawn_datetime}

def init_unique_timers():
    now = datetime.utcnow() + timedelta(hours=8)  # UTC+8
    for monster, interval in UNIQUE_MONSTERS.items():
        unique_timers[monster] = now + timedelta(minutes=interval)

# -----------------------------
# Keep Alive
# -----------------------------
keep_alive()
init_unique_timers()

# -----------------------------
# Events
# -----------------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    if not check_timers.is_running():
        check_timers.start()

# -----------------------------
# Commands
# -----------------------------
@bot.tree.command(name="ping", description="Check if bot is alive")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong! I'm awake!")

# Add boss/unique
@bot.tree.command(name="add", description="Add a boss or unique monster timer")
async def add(interaction: discord.Interaction, name: str):
    now = datetime.utcnow() + timedelta(hours=8)
    if name in BOSSES:
        respawn = now + timedelta(hours=BOSSES[name])
        boss_timers[name] = respawn
        await interaction.response.send_message(f"✅ Added world boss **{name}**. Respawn at {respawn.strftime('%I:%M %p')}")
    elif name in UNIQUE_MONSTERS:
        respawn = now + timedelta(minutes=UNIQUE_MONSTERS[name])
        unique_timers[name] = respawn
        await interaction.response.send_message(f"✅ Added unique monster **{name}**. Respawn at {respawn.strftime('%I:%M %p')}")
    else:
        await interaction.response.send_message(f"❌ Unknown boss/monster: {name}")

# Remove boss/unique
@bot.tree.command(name="remove", description="Remove a boss or unique monster timer")
async def remove(interaction: discord.Interaction, name: str):
    removed = False
    if name in boss_timers:
        del boss_timers[name]
        removed = True
    if name in unique_timers:
        del unique_timers[name]
        removed = True
    if removed:
        await interaction.response.send_message(f"✅ Removed **{name}** timer.")
    else:
        await interaction.response.send_message(f"❌ No active timer found for **{name}**.")

# -----------------------------
# Background Task
# -----------------------------
@tasks.loop(minutes=1)
async def check_timers():
    now = datetime.utcnow() + timedelta(hours=8)
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("❌ Channel not found")
        return

    # World bosses reminders
    for boss, respawn in list(boss_timers.items()):
        if now >= respawn - timedelta(minutes=2):
            await channel.send(f"⚔️ **{boss}** will spawn in ~2 minutes!")
            del boss_timers[boss]

    # Unique monsters reminders
    for monster, respawn in list(unique_timers.items()):
        if now >= respawn - timedelta(minutes=1):
            await channel.send(f"🔥 **{monster}** will spawn in ~1 minute!")
            del unique_timers[monster]

# -----------------------------
# Run Bot Async (so Flask keeps running)
# -----------------------------
async def main():
    await bot.start(TOKEN)

asyncio.run(main())
