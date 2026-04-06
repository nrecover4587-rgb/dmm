import asyncio
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from motor.motor_asyncio import AsyncIOMotorClient
from config import *

# ---------------- Mongo ----------------
mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo["BroadcastManager"]
sessions_col = db["sessions"]

# ---------------- Bot ----------------
bot = TelegramClient("dm-bot", API_ID, API_HASH)

clients = {}

# ---------------- START CLIENTS ----------------
async def start_clients():
    docs = await sessions_col.find({}).to_list(length=1000)

    for s in docs:
        try:
            cli = TelegramClient(StringSession(s["string"]), API_ID, API_HASH)
            await cli.connect()

            if not await cli.is_user_authorized():
                print(f"❌ Session expired: {s['tg_id']}")
                continue

            me = await cli.get_me()

            clients[s["tg_id"]] = {
                "client": cli,
                "name": f"{me.first_name or ''} {(me.last_name or '')}".strip(),
                "username": f"@{me.username}" if me.username else "NoUsername",
                "id": s["tg_id"]
            }

            print(f"✅ Loaded: {me.first_name}")

        except Exception as e:
            print("CLIENT ERROR:", e)


# ---------------- GLOBAL DM LISTENER ----------------
async def dm_listener():
    for acc_id, data in clients.items():
        cli = data["client"]

        @cli.on(events.NewMessage(incoming=True))
        async def handler(event, acc_id=acc_id, data=data):

            try:
                if not event.is_private:
                    return

                user = await event.get_sender()
                if not user:
                    return

                msg = f"""📩 DM MESSAGE

👤 User: {user.first_name}
🆔 USER_ID:{user.id}

🤖 Account: {data['name']}
🔗 Username: {data['username']}
🆔 ACCOUNT_ID:{acc_id}

🕒 Time: {datetime.now().strftime("%H:%M:%S")}

💬 Message:
{event.raw_text or "Media"}
"""

                await bot.send_message(DM_LOGGER_ID, msg)

            except Exception as e:
                print("DM ERROR:", e)

        await cli.start()


# ---------------- REPLY SYSTEM ----------------
@bot.on(events.NewMessage)
async def reply_handler(event):
    if event.chat_id != DM_LOGGER_ID or not event.is_reply:
        return

    try:
        reply = await event.get_reply_message()
        data = reply.text

        if "USER_ID:" not in data or "ACCOUNT_ID:" not in data:
            return

        user_id = int(data.split("USER_ID:")[1].split("\n")[0])
        acc_id = int(data.split("ACCOUNT_ID:")[1].split("\n")[0])

        cli = clients.get(acc_id, {}).get("client")

        if not cli:
            return await event.reply("❌ Account not found")

        if event.message.media:
            path = await event.download_media()
            await cli.send_file(user_id, path, caption=event.text or "")
        else:
            await cli.send_message(user_id, event.text)

        await event.reply("✅ Sent")

    except Exception as e:
        await event.reply(f"❌ Error: {e}")


# ---------------- MAIN ----------------
async def main():
    await bot.start(bot_token=BOT_TOKEN)
    await start_clients()
    await dm_listener()

    print("🚀 DM BOT RUNNING")
    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
