import asyncio
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from motor.motor_asyncio import AsyncIOMotorClient
from config import *

# ---------------- DB ----------------
mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo["BroadcastManager"]
sessions_col = db["sessions"]

# ---------------- BOT ----------------
bot = TelegramClient("dm-bot", API_ID, API_HASH)

clients = {}

# ---------------- LOAD ACCOUNTS ----------------
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

            acc_id = s["tg_id"]
            acc_name = f"{me.first_name or ''} {(me.last_name or '')}".strip()
            acc_username = f"@{me.username}" if me.username else "NoUsername"

            clients[acc_id] = cli

            # ---------------- DM HANDLER ----------------
            @cli.on(events.NewMessage(incoming=True))
            async def dm_handler(event, acc_id=acc_id, acc_name=acc_name, acc_username=acc_username):

                if not event.is_private:
                    return

                try:
                    user = await event.get_sender()
                    if not user:
                        return

                    user_id = user.id

                    msg = f"""📩 DM MESSAGE

👤 User: {user.first_name}
🆔 USER_ID:{user_id}

🤖 Account: {acc_name}
🔗 Username: {acc_username}
🆔 ACCOUNT_ID:{acc_id}

🕒 Time: {datetime.now().strftime("%H:%M:%S")}

💬 Message:
{event.raw_text or "Media"}
"""

                    print("📩 DM RECEIVED:", user_id)

                    await bot.send_message(DM_LOGGER_ID, msg)

                except Exception as e:
                    print("DM ERROR:", e)

            await cli.start()
            print(f"✅ Running: {acc_name}")

        except Exception as e:
            print("CLIENT ERROR:", e)


# ---------------- REPLY SYSTEM ----------------
@bot.on(events.NewMessage)
async def reply_handler(event):

    if event.chat_id != DM_LOGGER_ID or not event.is_reply:
        return

    try:
        reply = await event.get_reply_message()
        data = reply.text

        if not data:
            return
        if "USER_ID:" not in data or "ACCOUNT_ID:" not in data:
            return
        if not data.startswith("📩"):
            return

        user_id = int(data.split("USER_ID:")[1].split("\n")[0])
        acc_id = int(data.split("ACCOUNT_ID:")[1].split("\n")[0])

        cli = clients.get(acc_id)

        if not cli:
            return await event.reply("❌ Account not active")

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

    print("🚀 DM LOGGER BOT RUNNING")
    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
