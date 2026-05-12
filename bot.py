import discord
from discord.ext import tasks, commands
from discord import app_commands
import json
import os
from datetime import datetime, timedelta, timezone

# =====================
# KEEP ALIVE WEB SERVER
# =====================
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive")

def run_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

threading.Thread(target=run_server).start()

# =====================
# TOKEN
# =====================
TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN is None:
    raise ValueError("DISCORD_TOKEN is not set!")

# =====================
# DISCORD SETUP
# =====================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "conversations.json"
CUSTOM_REMINDER_FILE = "custom_reminders.json"

# =====================
# LOAD DATA
# =====================
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        conversations = json.load(f)
else:
    conversations = {}

if os.path.exists(CUSTOM_REMINDER_FILE):
    with open(CUSTOM_REMINDER_FILE, "r") as f:
        custom_reminders = json.load(f)
else:
    custom_reminders = []

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(conversations, f, indent=4)

    with open(CUSTOM_REMINDER_FILE, "w") as f:
        json.dump(custom_reminders, f, indent=4)

# =====================
# TIME PARSER
# =====================
def parse_time(timestr):
    unit = timestr[-1]
    amount = int(timestr[:-1])

    if unit == "m":
        return timedelta(minutes=amount)
    elif unit == "h":
        return timedelta(hours=amount)
    elif unit == "d":
        return timedelta(days=amount)
    else:
        return None

# =====================
# READY EVENT
# =====================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(e)

    check_reminders.start()
    check_custom_reminders.start()

# =====================
# MESSAGE TRACKING
# =====================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.mentions:
        sender_id = str(message.author.id)

        for user in message.mentions:
            receiver_id = str(user.id)

            if sender_id == receiver_id:
                continue

            key = f"{sender_id}-{receiver_id}"

            conversations[key] = {
                "sender": sender_id,
                "receiver": receiver_id,
                "channel": message.channel.id,
                "start_time": datetime.now(timezone.utc).isoformat(),
                "replied": False,
                "reminders_sent": []
            }

            save_data()

    # mark replied
    for key in conversations:
        convo = conversations[key]

        if str(message.author.id) == convo["receiver"]:
            convo["replied"] = True

    # cancel custom reminders if user replied
    for reminder in custom_reminders:
        if (
            str(message.author.id) == reminder["target"]
            and not reminder["sent"]
        ):
            reminder["cancelled"] = True

    save_data()

    await bot.process_commands(message)

# =====================
# AUTO REMINDERS
# =====================
@tasks.loop(hours=1)
async def check_reminders():
    now = datetime.now(timezone.utc)

    for key in list(conversations.keys()):
        convo = conversations[key]

        if convo["replied"]:
            continue

        start_time = datetime.fromisoformat(convo["start_time"])
        time_passed = now - start_time

        channel = bot.get_channel(convo["channel"])

        if channel is None:
            continue

        user = await bot.fetch_user(int(convo["receiver"]))

        if time_passed < timedelta(hours=24):
            continue

        schedule = [
            (1, "1-day"),
            (3, "3-day"),
            (7, "7-day"),
            (14, "14-day")
        ]

        for days, label in schedule:
            if (
                time_passed >= timedelta(days=days)
                and label not in convo["reminders_sent"]
            ):
                await channel.send(
                    f"{user.mention} reminder: you still haven't replied."
                )

                convo["reminders_sent"].append(label)
                save_data()

# =====================
# CUSTOM REMINDER LOOP
# =====================
@tasks.loop(minutes=1)
async def check_custom_reminders():
    now = datetime.now(timezone.utc)

    for reminder in custom_reminders:
        if reminder.get("sent"):
            continue

        if reminder.get("cancelled"):
            continue

        remind_time = datetime.fromisoformat(reminder["remind_time"])

        if now >= remind_time:
            channel = bot.get_channel(reminder["channel"])

            if channel:
                user = await bot.fetch_user(int(reminder["target"]))

                await channel.send(
                    f"{user.mention} reminder: {reminder['message']}"
                )

            reminder["sent"] = True
            save_data()

# =====================
# /REMIND COMMAND
# =====================
@bot.tree.command(name="remind", description="Set a custom reminder")
async def remind(
    interaction: discord.Interaction,
    user: discord.User,
    time: str,
    message: str
):
    delta = parse_time(time)

    if delta is None:
        await interaction.response.send_message(
            "Invalid time format. Use m/h/d (example: 10m, 2h, 3d)",
            ephemeral=True
        )
        return

    remind_time = datetime.now(timezone.utc) + delta

    custom_reminders.append({
        "target": str(user.id),
        "channel": interaction.channel.id,
        "guild": interaction.guild.id,
        "message": message,
        "remind_time": remind_time.isoformat(),
        "sent": False,
        "cancelled": False
    })

    save_data()

    await interaction.response.send_message(
        f"Reminder set for {user.mention} in {time}"
    )

# =====================
# /CALENDAR COMMAND
# =====================
@bot.tree.command(name="calendar", description="View all pending reminders in this server")
async def calendar(interaction: discord.Interaction):

    guild_id = interaction.guild.id

    active_reminders = []

    for reminder in custom_reminders:
        if (
            reminder.get("guild") == guild_id
            and not reminder.get("sent")
            and not reminder.get("cancelled")
        ):
            active_reminders.append(reminder)

    if not active_reminders:
        await interaction.response.send_message(
            "No active reminders in this server."
        )
        return

    message_lines = []

    for reminder in active_reminders:
        user = await bot.fetch_user(int(reminder["target"]))

        remind_time = datetime.fromisoformat(
            reminder["remind_time"]
        ).strftime("%Y-%m-%d %H:%M UTC")

        line = (
            f"• {user.name} — {reminder['message']} "
            f"({remind_time})"
        )

        message_lines.append(line)

    final_message = "\n".join(message_lines)

    if len(final_message) > 1900:
        final_message = final_message[:1900] + "\n..."

    await interaction.response.send_message(final_message)

bot.run(TOKEN)
