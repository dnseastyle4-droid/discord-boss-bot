import os
import asyncio
from datetime import datetime, timedelta, timezone
import discord
from discord.ext import commands, tasks
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
CHANNEL_ID = int(os.getenv("CHANNEL"))  # Channel for reminders

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ---------------- Boss Data ---------------- #

# Respawn bosses (minutes)
RESPAWN_BOSSES = {
    "supore": 62, "asta": 62, "secreta": 62, "ordo": 62,
    "gareth": 32, "shuliar": 35, "larba": 35, "catena": 35,
    "titore": 37, "duplican": 48, "metus": 48, "wannitas": 48
}

# Scheduled bosses (specific times in PH time, UTC+8)
SCHEDULED_BOSSES = {
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

# Unique monsters (always 15 min respawn)
UNIQUE_MONSTERS = {
    "blood mother", "decoy", "ghost webber", "shadow webber",
    "escort leader maximus", "fortuneteller ariel", "priest petroca",
    "sylandra", "halfmoon stone turtle", "cobolt blitz captain",
    "black wings", "forgotten olive", "deadman's grow", "cassandra",
    "mutated scorpion", "berserk higher harpy",
    "red lizardman patrol captain", "lyrian", "durian", "infected kukri",
    "straggler brown", "veridon", "shaug blitz captain",
    "shaug high-ranking wizard", "shaug patrol captain",
    "elder lich", "catena's eye", "elder scorpius", "catena's servant",
    "catena's cry", "catena's ego", "catena's rage", "catena's sorrow"
}

# Destroyer bosses (fixed daily schedule, notify once)
DESTROYER_BOSSES = {
    "ratan": [("11:00", "12:00"), ("20:00", "21:00")],
    "parto": [("11:00", "12:00"), ("20:00", "21:00")],
    "nedra": [("11:00", "12:00"), ("20:00", "21:00")]
}

# ---------------- Storage ---------------- #
pending_bosses = {}   # {boss_name: expire_time}
notified_destroyers = set()  # track daily destroyer reminders

# ---------------- Helpers ---------------- #

def ph_time_now():
    return datetime.now(timezone.utc) + timedelta(hours=8)

def normalize(name: str):
    return name.lower().strip()

# ---------------- Commands ---------------- #

@tree.command(name="help", description="Show how to use the bot")
async def help_cmd(interaction: discord.Interaction):
    msg = (
        "**📜 Boss Bot Commands:**\n"
        "`/add <boss>` → Track a boss or unique monster.\n"
        "`/remove <boss>` → Remove a pending boss.\n"
        "`/status` → Show currently tracked bosses.\n\n"
        "**Notes:**\n"
        "- Names are not case-sensitive.\n"
        "- Respawn bosses follow their timers.\n"
        "- Unique monsters always 15m respawn.\n"
        "- Destroyers (Ratan, Parto, Nedra) auto-remind once per slot.\n"
    )
    await interaction.response.send_message(msg, ephemeral=True)

@tree.command(name="add", description="Add a boss or unique monster timer")
@app_commands.describe(name="Name of the boss")
async def add_cmd(interaction: discord.Interaction, name: str):
    boss = normalize(name)
    now = ph_time_now()

    if boss in DESTROYER_BOSSES:
        await interaction.response.send_message(f"⚔️ {name} is a Destroyer Boss. Notifications are automatic.", ephemeral=True)
        return

    if boss in UNIQUE_MONSTERS:
        expire = now + timedelta(minutes=15)
        pending_bosses[boss] = expire
        await interaction.response.send_message(f"✅ Added {name} (15m respawn).", ephemeral=True)
        return

    if boss in RESPAWN_BOSSES:
        expire = now + timedelta(minutes=RESPAWN_BOSSES[boss])
        pending_bosses[boss] = expire
        await interaction.response.send_message(f"✅ Added {name} ({RESPAWN_BOSSES[boss]}m respawn).", ephemeral=True)
        return

    if boss in SCHEDULED_BOSSES:
        await interaction.response.send_message(f"🕑 {name} is a scheduled boss. It will notify automatically.", ephemeral=True)
        return

    await interaction.response.send_message(f"❌ Unknown boss: {name}", ephemeral=True)

@tree.command(name="remove", description="Remove a boss from tracking")
async def remove_cmd(interaction: discord.Interaction, name: str):
    boss = normalize(name)
    if boss in pending_bosses:
        pending_bosses.pop(boss)
        await interaction.response.send_message(f"🗑️ Removed {name} from pending.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ {name} not found in pending list.", ephemeral=True)

@tree.command(name="status", description="Show pending bosses")
async def status_cmd(interaction: discord.Interaction):
    if not pending_bosses:
        await interaction.response.send_message("📭 No pending bosses right now.", ephemeral=True)
        return

    now = ph_time_now()
    lines = []
    for boss, expire in pending_bosses.items():
        mins = int((expire - now).total_seconds() // 60)
        if mins > 0:
            lines.append(f"- {boss.title()} (in {mins}m)")
    msg = "\n".join(lines) if lines else "📭 No active pending bosses."
    await interaction.response.send_message(msg, ephemeral=True)

# ---------------- Background Tasks ---------------- #

@tasks.loop(minutes=1)
async def reminder_loop():
    channel = bot.get_channel(CHANNEL_ID)
    now = ph_time_now()

    # Check pending bosses
    expired = []
    for boss, expire in pending_bosses.items():
        if now >= expire:
            await channel.send(f"⏰ **{boss.title()}** has respawned!")
            expired.append(boss)
    for boss in expired:
        pending_bosses.pop(boss, None)

    # Check scheduled bosses (notify only if within 2–3 hours)
    weekday = now.strftime("%A").lower()
    for boss, schedules in SCHEDULED_BOSSES.items():
        for day, t in schedules:
            if weekday == day:
                h, m = map(int, t.split(":"))
                event_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
                delta = (event_time - now).total_seconds() / 3600
                if 0 < delta <= 3:
                    key = f"{boss}-{event_time}"
                    if key not in pending_bosses:
                        pending_bosses[key] = event_time
                        await channel.send(f"📢 Scheduled Boss **{boss.title()}** coming at {t}!")

    # Destroyer bosses (fixed windows, notify once per slot)
    for boss, slots in DESTROYER_BOSSES.items():
        for start, end in slots:
            start_h, start_m = map(int, start.split(":"))
            end_h, end_m = map(int, end.split(":"))
            start_time = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
            end_time = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
            if start_time <= now <= end_time:
                key = f"{boss}-{start}"
                if key not in notified_destroyers:
                    notified_destroyers.add(key)
                    await channel.send(f"🔥 Destroyer Boss **{boss.title()}** active between {start} - {end}!")

# ---------------- Events ---------------- #

@bot.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    reminder_loop.start()
    print(f"✅ Logged in as {bot.user}")

# ---------------- Run ---------------- #

bot.run(TOKEN)
