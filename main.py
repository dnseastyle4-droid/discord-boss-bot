# main.py
import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, time
from flask import Flask

# -----------------------------
# Environment Variables
# -----------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
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
    "Venatus": 10, "Viorent": 10, "Ego": 21, "Livera": 24, "Araneo": 21,
    "Undomiel": 24, "Lady Dalia": 18, "General Aquleus": 29,
    "Amentis": 29, "Baron Braudmore": 32
}
UNIQUE_MONSTERS = {
    "Outlaw Kaiser":15, "Screaming Wings":15, "Suspicious Wizard":15,
    "Dark Apparition":15, "Brutal Butcher":15, "Corrupted Shellbug":15,
    "Secret Creation":15, "Magic Puppet":15, "Wizard's Puppet":15,
    "Lamia Shaman":15, "Angusto":15, "Berserk Thardus":15, "Ancient Thardus":15,
    "Charging Thardus":15, "Desert Golem":15, "Alarak":15, "Ancient Turtle":15,
    "Protector of the Ruins":15, "Black Hand":15, "Ancient Protector":15,
    "Black Wedge":15, "Intikam":15, "Desert Protector":15
}
DESTROYER_BOSSES = ["Ratan","Parto","Nedra"]

# -----------------------------
# Timer storage
# -----------------------------
boss_timers = {}         # {boss: respawn_datetime}
added_unique = set()     # names of active unique monsters
unique_timers = {}       # {unique_name: spawn_datetime}
destroyer_notified = set()   # destroyer notifications

# -----------------------------
# Flask app for uptime monitoring
# -----------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

# -----------------------------
# Helper Functions
# -----------------------------
def get_channel():
    return bot.get_channel(CHANNEL_ID)

def utc_now():
    return datetime.utcnow() + timedelta(hours=8)

def format_time(dt):
    return dt.strftime("%I:%M %p")  # 12-hour format

# -----------------------------
# Init unique timers
# -----------------------------
for u, mins in UNIQUE_MONSTERS.items():
    unique_timers[u.lower()] = utc_now() + timedelta(minutes=mins)

# -----------------------------
# Slash Commands
# -----------------------------
@bot.tree.command(name="add", description="Add a boss or unique monster timer")
async def add(interaction: discord.Interaction, boss: str):
    boss = boss.lower()
    now = utc_now()
    # World Boss
    for wboss, hrs in BOSSES.items():
        if boss == wboss.lower():
            respawn = now + timedelta(hours=hrs)
            boss_timers[wboss] = respawn
            await interaction.response.send_message(f"✅ {wboss} added! Spawns at {format_time(respawn)}")
            return
    # Unique Monster
    for umon in UNIQUE_MONSTERS:
        if boss == umon.lower():
            if umon in added_unique:
                await interaction.response.send_message(f"⚠️ {umon} already added!")
                return
            spawn = now + timedelta(minutes=UNIQUE_MONSTERS[umon])
            unique_timers[umon] = spawn
            added_unique.add(umon)
            await interaction.response.send_message(f"🔥 {umon} added! Spawns at {format_time(spawn)}")
            return
    await interaction.response.send_message("❌ Boss/Monster not found!")

@bot.tree.command(name="remove", description="Remove a boss or unique monster timer")
async def remove(interaction: discord.Interaction, boss: str):
    boss = boss.lower()
    removed = False
    for wboss in list(boss_timers):
        if boss == wboss.lower():
            del boss_timers[wboss]
            removed = True
    for umon in list(added_unique):
        if boss == umon.lower():
            added_unique.remove(umon)
            removed = True
    await interaction.response.send_message("✅ Timer removed!" if removed else "❌ Nothing to remove.")

@bot.tree.command(name="status", description="View pending bosses")
async def status(interaction: discord.Interaction):
    msg = "**Pending Bosses/Monsters:**\n"
    if boss_timers:
        msg += "\n**World Bosses:**\n" + "\n".join(f"{b} at {format_time(t)}" for b,t in boss_timers.items())
    if added_unique:
        msg += "\n**Unique Monsters:**\n" + "\n".join(f"{u} at {format_time(unique_timers[u])}" for u in added_unique)
    if not boss_timers and not added_unique:
        msg += "None!"
    await interaction.response.send_message(msg)

@bot.tree.command(name="help", description="Show bot usage")
async def help_cmd(interaction: discord.Interaction):
    text = (
        "**Commands:**\n"
        "/add <boss_name> - Add a boss or unique monster timer\n"
        "Example: `/add Alarak` or `/add Undomiel`\n"
        "/remove <boss_name> - Remove a timer\n"
        "/status - View pending bosses/monsters\n"
        "Destroyers: Ratan, Parto, Nedra notify automatically in their time windows"
    )
    await interaction.response.send_message(text)

# -----------------------------
# Background Task
# -----------------------------
notified_world = set()
notified_unique = set()

@tasks.loop(minutes=1)
async def check_timers():
    now = utc_now()
    channel = get_channel()
    if not channel:
        return

    # --- World Bosses ---
    for boss, respawn in list(boss_timers.items()):
        if boss not in notified_world and now >= respawn - timedelta(minutes=2):
            await channel.send(f"⚔️ **{boss}** will spawn in ~2 minutes! Prepare!")
            notified_world.add(boss)
            del boss_timers[boss]

    # --- Unique Monsters ---
    for u in list(added_unique):
        spawn_time = unique_timers[u]
        if u not in notified_unique and now >= spawn_time - timedelta(minutes=1) and now < spawn_time:
            await channel.send(f"🔥 **{u}** will spawn in ~1 minute!")
            notified_unique.add(u)
        if now >= spawn_time:
            added_unique.remove(u)
            notified_unique.discard(u)

    # --- Destroyer Bosses ---
    for d in DESTROYER_BOSSES:
        windows = [(time(11,0), time(12,0)), (time(20,0), time(21,0))]
        in_window = any(w[0] <= now.time() <= w[1] for w in windows)
        if in_window and d not in destroyer_notified:
            await channel.send(f"💀 **{d}** is active now!")
            destroyer_notified.add(d)
        if not in_window and d in destroyer_notified:
            destroyer_notified.remove(d)

# -----------------------------
# Bot Ready
# -----------------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.tree.sync()
    if not check_timers.is_running():
        check_timers.start()

# -----------------------------
# Run Flask + Bot
# -----------------------------
if __name__ == "__main__":
    from threading import Thread
    Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()
    bot.run(TOKEN)
