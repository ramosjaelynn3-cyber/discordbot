import discord
from discord.ext import tasks
import json
import os
from datetime import datetime, timedelta, timezone

TOKEN = "MTUwMzc0MDI2NDQ2Njg3ODU2NQ.G95mMH._sbt0Fgwco3mOlHAyIAcqEVcOTfsv0PphAmOPE"

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

DATA_FILE = "conversations.json"

Load saved conversations
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        conversations = json.load(f)
else:
    conversations = {}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(conversations, f)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    check_reminders.start()

@client.event
async def on_message(message):
    if message.author.bot:
        return

    # Ignore messages without mentions
    if len(message.mentions) == 0:
        return

    sender_id = str(message.author.id)

    for mentioned_user in message.mentions:
        receiver_id = str(mentioned_user.id)

        # Skip self mentions
        if sender_id == receiver_id:
            continue

        conversation_key = f"{sender_id}-{receiver_id}"

        conversations[conversation_key] = {
            "sender": sender_id,
            "receiver": receiver_id,
            "channel": message.channel.id,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "replied": False,
            "reminders_sent": []
        }

        save_data()

    # Mark replies
    for key in list(conversations.keys()):
        convo = conversations[key]

        if str(message.author.id) == convo["receiver"]:
            convo["replied"] = True

    save_data()

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

        receiver = await client.fetch_user(int(convo["receiver"]))

        # Wait 24 hours before first reminder
        if time_passed < timedelta(hours=24):
            continue

        reminder_schedule = [
            (3, "3-day"),
            (7, "7-day"),
            (14, "14-day")
        ]

        for days, label in reminder_schedule:
            if (
                time_passed >= timedelta(days=days)
                and label not in convo["reminders_sent"]
            ):
                await channel.send(
                    f"{receiver.mention} reminder: you still have not replied."
                )

                convo["reminders_sent"].append(label)
                save_data()

client.run(TOKEN)
