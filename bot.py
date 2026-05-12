import discord
from discord.ext import tasks, commands
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

threading.Thread(target=run_server, daemon=True).start()

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
CUSTOM_FILE = "custom_reminders.json"

# =====================
# LOAD DATA
# =====================
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        conversations = json.load(f)
else:
    conversations = {}

if os.path.exists(CUSTOM_FILE):
    with open(CUSTOM_FILE, "r") as f:
        custom_reminders = json.load(f)
else:
    custom_reminders = []

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(conversations, f, indent=4)

    with open(CUSTOM_FILE, "w") as f:
        json.dump(custom_reminders, f, indent=4)

# =====================
# TIME PARSER
# =====================
def parse_time(t):
    try:
        unit = t[-1]
        value = int(t[:-1])

        if unit == "m":
            return timedelta(minutes=value)
        if unit == "h":
            return timedelta(hours=value)
        if unit == "d":
            return timedelta(days=value)

    except:
        return None

# =====================
# READY
# =====================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
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

    # CREATE AUTO TRACKERS
    if message.mentions:

        sender = str(message.author.id)

        for user in message.mentions:
            receiver = str(user.id)

            if sender == receiver:
                continue

            key = f"{sender}-{receiver}"

            conversations[key] = {
                "sender": sender,
                "receiver": receiver,
                "channel": message.channel.id,
                "guild": message.guild.id,
                "start_time": datetime.now(timezone.utc).isoformat(),
                "replied": False,
                "reminders_sent": []
            }

        save_data()

    # MARK REPLIES
    for convo in conversations.values():
        if str(message.author.id) == convo["receiver"]:
            convo["replied"] = True

    # CANCEL CUSTOM REMINDERS
    for r in custom_reminders:
        if str(message.author.id) == r["target"]:
            r["cancelled"] = True

    save_data()

    await bot.process_commands(message)

# =====================
# AUTO REMINDERS
# =====================
@tasks.loop(minutes=1)
async def check_reminders():
    now = datetime.now(timezone.utc)

    schedule = [
        (timedelta(minutes=5), "5m"),
        (timedelta(days=1), "1d"),
        (timedelta(days=3), "3d"),
        (timedelta(days=5), "5d"),
        (timedelta(days=7), "7d"),
        (timedelta(days=10), "10d"),
        (timedelta(days=14), "14d")
    ]

    for convo in conversations.values():

        if convo.get("replied"):
            continue

        try:
            start = datetime.fromisoformat(convo["start_time"])
            passed = now - start

            channel = bot.get_channel(convo["channel"])
            if not channel:
                continue

            user = await bot.fetch_user(int(convo["receiver"]))

            for delay, label in schedule:

                if passed >= delay and label not in convo["reminders_sent"]:

                    await channel.send(
                        f"{user.mention} reminder: you still haven't replied."
                    )

                    convo["reminders_sent"].append(label)
                    save_data()

        except:
            continue

# =====================
# CUSTOM REMINDERS
# =====================
@tasks.loop(minutes=1)
async def check_custom_reminders():
    now = datetime.now(timezone.utc)

    for r in custom_reminders:

        if r.get("sent") or r.get("cancelled"):
            continue

        try:
            when = datetime.fromisoformat(r["remind_time"])

            if now >= when:

                channel = bot.get_channel(r["channel"])
                user = await bot.fetch_user(int(r["target"]))

                if channel:
                    await channel.send(
                        f"{user.mention} reminder: {r['message']}"
                    )

                r["sent"] = True
                save_data()

        except:
            continue

# =====================
# /REMIND COMMAND
# =====================
@bot.tree.command(name="remind")
async def remind(interaction: discord.Interaction, user: discord.User, time: str, message: str):

    delta = parse_time(time)

    if not delta:
        await interaction.response.send_message(
            "Use format: 10m, 2h, 3d",
            ephemeral=True
        )
        return

    custom_reminders.append({
        "target": str(user.id),
        "channel": interaction.channel.id,
        "guild": interaction.guild.id,
        "message": message,
        "remind_time": (datetime.now(timezone.utc) + delta).isoformat(),
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
@bot.tree.command(name="calendar")
async def calendar(interaction: discord.Interaction):

    guild = interaction.guild.id
    lines = []

    # AUTO REMINDERS
    for convo in conversations.values():

        if convo.get("guild") != guild:
            continue

        if convo.get("replied"):
            continue

        try:
            sender = await bot.fetch_user(int(convo["sender"]))
            receiver = await bot.fetch_user(int(convo["receiver"]))

            time = datetime.fromisoformat(
                convo["start_time"]
            ).strftime("%Y-%m-%d %H:%M UTC")

            lines.append(
                f"📨 AUTO: {receiver.name} waiting on {sender.name} ({time})"
            )

        except:
            continue

    # CUSTOM REMINDERS
    for r in custom_reminders:

        if r.get("guild") != guild:
            continue

        if r.get("sent") or r.get("cancelled"):
            continue

        try:
            user = await bot.fetch_user(int(r["target"]))

            time = datetime.fromisoformat(
                r["remind_time"]
            ).strftime("%Y-%m-%d %H:%M UTC")

            lines.append(
                f"⏰ CUSTOM: {user.name} — {r['message']} ({time})"
            )

        except:
            continue

    if not lines:
        await interaction.response.send_message("No active reminders.")
        return

    msg = "\n".join(lines)

    if len(msg) > 1900:
        msg = msg[:1900] + "..."

    await interaction.response.send_message(msg)

bot.run(TOKEN)
