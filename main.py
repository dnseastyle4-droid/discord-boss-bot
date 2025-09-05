import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, timezone

# ==============================
# CONFIG
# ==============================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")  # remove default help

CHANNEL_IDS = [
    int(cid) for cid in os.getenv("CHANNELS", "").split(",") if cid.strip().isdigit()
]

# Manila time (UTC+8)
PH_TIMEZONE = timezone(timedelta(hours=8))

# Track pending bosses
pending_bosses = {}

# ==============================
# BOSSES
# ==============================
unique_monsters = {
    "alarak", "black wedge", "dark apparition", "suspicious wizard", "thardus",
    "blood mother", "decoy", "ghost webber", "shadow webber",
    "escort leader maximus", "fortuneteller ariel", "priest petroca",
    "sylandra", "halfmoon stone turtle", "cobolt blitz captain", "black wings",
    "forgotten olive", "deadman's grow", "cassandra", "mutated scorpion",
    "berserk higher harpy", "red lizardman patrol captain", "lyrian", "durian",
    "infected kukri", "straggler brown", "veridon", "shaug blitz captain",
    "shaug high-ranking wizard", "shaug patrol captain", "elder lich",
    "catena's eye", "elder scorpius", "catena's servant", "catena's cry",
    "catena's ego", "catena's rage", "catena's sorrow"
}

scheduled_bosses = {
    "clemantis": [("monday", "11:30"), ("thursday", "19:00")],
    "saphirus": [("sunday", "17:00"), ("tuesday", "11:30")],
    "neutro": [("tuesday", "19:00"), ("thursday", "11:30")],
    "thymele": [("monday", "19:00"), ("wednesday", "11:30")],
    "milavy": [("saturday", "15:00")],
    "ringor": [("saturday", "17:00")],
    "roderick": [("friday", "19:00")],
    "auraq": [("sunday", "21:00"), ("wednesday", "21:00")],
    "chailflock": [("saturday", "22:00")]
}

destroyers = {"ratan", "parto", "nedra"}

# Respawn times (minutes)
respawn_times = {
    "supore": 62, "asta": 62, "secreta": 62, "ordo": 62,
    "gareth": 32, "shuliar": 35, "larba": 35, "catena": 35,
    "titore": 37, "duplican": 48, "metus": 48, "wannitas": 48
}

# ==============================
# EVENTS
# ==============================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")
    reminder_loop.start()

# ==============================
# SLASH COMMANDS
# ==============================
@bot.tree.command(name="add", description="Add a boss to the tracking list")
async def add(interaction: discord.Interaction, name: str):
    boss = name.lower().strip()

    now = datetime.now(PH_TIMEZONE)

    # Destroyer bosses → notify once
    if boss in destroyers:
        await notify_channels(f"💥 Destroyer boss **{name.title()}** has spawned! (One-time)")
        await interaction.response.send_message(f"✅ Added {name.title()} (destroyer).", ephemeral=True)
        return

    # Scheduled bosses → auto handled, don't add manually
    if boss in scheduled_bosses:
        await interaction.response.send_message(
            f"⏰ {name.title()} is a scheduled boss and will be auto-tracked.",
            ephemeral=True
        )
        return

    # Respawn / Unique monsters
    respawn = respawn_times.get(boss, 15)  # default 15 mins
    if boss in pending_bosses:
        await interaction.response.send_message(f"⚠️ {name.title()} is already being tracked.", ephemeral=True)
        return

    spawn_time = now + timedelta(minutes=respawn)
    pending_bosses[boss] = spawn_time
    await interaction.response.send_message(f"✅ Added {name.title()} (respawns in {respawn} mins).", ephemeral=True)

@bot.tree.command(name="status", description="Show pending bosses")
async def status(interaction: discord.Interaction):
    if not pending_bosses:
        await interaction.response.send_message("📋 No pending bosses right now.", ephemeral=True)
        return

    now = datetime.now(PH_TIMEZONE)
    lines = []
    for boss, spawn_time in pending_bosses.items():
        remaining = int((spawn_time - now).total_seconds() // 60)
        if remaining > 0:
            lines.append(f"**{boss.title()}** → {remaining} mins left")

    if not lines:
        await interaction.response.send_message("📋 No pending bosses right now.", ephemeral=True)
    else:
        await interaction.response.send_message("📋 Pending Bosses:\n" + "\n".join(lines), ephemeral=True)

@bot.tree.command(name="guide", description="Show how to use the bot")
async def guide(interaction: discord.Interaction):
    msg = (
        "📖 **Boss Bot Guide**\n"
        "• `/add <boss>` → Track a boss (case-insensitive).\n"
        "• `/status` → Check pending bosses.\n"
        "• `/guide` → Show this help guide.\n\n"
        "⚔️ **Notes**:\n"
        "• Unique monsters respawn every 15 mins.\n"
        "• Destroyers (Ratan, Parto, Nedra) notify once only.\n"
        "• Scheduled bosses are automatically tracked."
    )
    await interaction.response.send_message(msg, ephemeral=True)

# ==============================
# REMINDER LOOP
# ==============================
@tasks.loop(minutes=1)
async def reminder_loop():
    now = datetime.now(PH_TIMEZONE)

    # Check pending bosses
    to_remove = []
    for boss, spawn_time in pending_bosses.items():
        if now >= spawn_time:
            await notify_channels(f"⚔️ **{boss.title()}** has respawned!")
            to_remove.append(boss)
    for boss in to_remove:
        del pending_bosses[boss]

    # Check scheduled bosses
    weekday = now.strftime("%A").lower()
    current_time = now.strftime("%H:%M")

    for boss, times in scheduled_bosses.items():
        for day, t in times:
            if weekday == day and current_time == t:
                await notify_channels(f"⏰ Scheduled boss **{boss.title()}** has spawned!")

# ==============================
# HELPERS
# ==============================
async def notify_channels(message: str):
    for channel_id in CHANNEL_IDS:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(message)

# ==============================
# RUN BOT
# ==============================
bot.run(os.getenv("DISCORD_TOKEN"))
