import discord
from discord.ext import tasks
import json
import os
from datetime import datetime, timedelta, timezone

# =====================
# TOKEN (HOSTING SAFE)
# =====================
TOKEN = os.getenv("MTUwMzc0MDI2NDQ2Njg3ODU2NQ.G95mMH._sbt0Fgwco3mOlHAyIAcqEVcOTfsv0PphAmOPE")

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
# BOT READY
# =====================
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    check_reminders.start()

# =====================
# MESSAGE HANDLER
# =====================
@client.event
async def on_message(message):
    if message.author.bot:
        return

    if len(message.mentions) == 0:
        return

    sender_id = str(message.author.id)

    for mentioned_user in message.mentions:
        receiver_id = str(mentioned_user.id)

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

    # mark replies
    for key in conversations:
        convo = conversations[key]
        if str(message.author.id) == convo["receiver"]:
            convo["replied"] = True

    save_data()

# =====================
# REMINDER LOOP (TEST MODE FIRST)
# =====================
@tasks.loop(seconds=10)
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

        receiver = await client.fetch_user(int(convo["receiver"]))

        # 🔥 TEST MODE: 10 seconds
        if time_passed < timedelta(seconds=10):
            continue

        schedule = [
            (10, "10s"),
            (20, "20s"),
            (40, "40s")
        ]

        for sec, label in schedule:
            if time_passed >= timedelta(seconds=sec) and label not in convo["reminders_sent"]:
                await channel.send(
                    f"{receiver.mention} reminder test ({label})"
                )

                convo["reminders_sent"].append(label)
                save_data()

client.run(TOKEN)
