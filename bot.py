import discord
from discord.ext import tasks
import json
import os
from datetime import datetime, timedelta, timezone

# =====================
# KEEP ALIVE WEB SERVER (for UptimeRobot)
# =====================
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive")

def run_server():
    server = HTTPServer(("0.0.0.0", 8080), Handler)
    server.serve_forever()

threading.Thread(target=run_server).start()

# =====================
# DISCORD TOKEN
# =====================
TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN is None:
    raise ValueError("DISCORD_TOKEN is not set!")

# =====================
# DISCORD SETUP
# =====================
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

DATA_FILE = "conversations.json"

# =====================
# LOAD DATA
# =====================
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        conversations = json.load(f)
else:
    conversations = {}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(conversations, f, indent=4)

# =====================
# READY EVENT
# =====================
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    check_reminders.start()

# =====================
# MESSAGE TRACKING
# =====================
@client.event
async def on_message(message):
    if message.author.bot:
        return

    if not message.mentions:
        return

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

    for key in conversations:
        convo = conversations[key]
        if str(message.author.id) == convo["receiver"]:
            convo["replied"] = True

    save_data()

# =====================
# REMINDER SYSTEM
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

        channel = client.get_channel(convo["channel"])
        if channel is None:
            continue

        user = await client.fetch_user(int(convo["receiver"]))

        if time_passed < timedelta(hours=24):
            continue

        schedule = [
            (1, "1-day"),
            (3, "3-day"),
            (7, "7-day"),
            (14, "14-day")
        ]

        for days, label in schedule:
            if time_passed >= timedelta(days=days) and label not in convo["reminders_sent"]:
                await channel.send(f"{user.mention} reminder: you still haven't replied.")
                convo["reminders_sent"].append(label)
                save_data()

client.run(TOKEN)
