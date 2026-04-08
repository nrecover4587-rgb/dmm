import asyncio
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import AuthKeyUnregisteredError, SessionRevokedError
from motor.motor_asyncio import AsyncIOMotorClient

# ========= CONFIG =========
API_ID = 12345
API_HASH = "your_api_hash"
BOT_TOKEN = "your_bot_token"
MONGO_URL = "your_mongo_url"

LOGGER_ID = -1001234567890
OWNER_IDS = [123456789]

# ========= MONGO =========
mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo["ManagerBot"]

sessions_col = db["sessions"]
tracked_col = db["tracked_users"]

# ========= BOT =========
bot = TelegramClient("manager-bot", API_ID, API_HASH)


# ========= HELPERS =========
def is_owner(uid):
    return uid in OWNER_IDS


async def send_log(text):
    try:
        await bot.send_message(LOGGER_ID, text)
    except:
        print(text)


# ========= ADD SESSION =========
@bot.on(events.NewMessage(pattern=r"^/add\s+(.+)$"))
async def add_session(event):
    if not is_owner(event.sender_id):
        return await event.reply("❌ Not owner")

    sess = event.pattern_match.group(1)

    cli = TelegramClient(StringSession(sess), API_ID, API_HASH)

    try:
        await cli.start()
        me = await cli.get_me()

        await sessions_col.update_one(
            {"tg_id": me.id},
            {"$set": {
                "tg_id": me.id,
                "string": sess,
                "name": me.first_name
            }},
            upsert=True
        )

        await event.reply(f"✅ Session added `{me.id}`")

    except Exception as e:
        await event.reply(f"❌ Invalid session: {e}")

    finally:
        await cli.disconnect()


# ========= ADD USER =========
@bot.on(events.NewMessage(pattern=r"^/adduser\s+(\d+)$"))
async def add_user(event):
    if not is_owner(event.sender_id):
        return await event.reply("❌ Not owner")

    user_id = int(event.pattern_match.group(1))

    await tracked_col.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "added_at": datetime.utcnow()}},
        upsert=True
    )

    await event.reply(f"✅ User added `{user_id}`")


# ========= REMOVE USER =========
@bot.on(events.NewMessage(pattern=r"^/rmuser\s+(\d+)$"))
async def remove_user(event):
    if not is_owner(event.sender_id):
        return await event.reply("❌ Not owner")

    user_id = int(event.pattern_match.group(1))

    res = await tracked_col.delete_one({"user_id": user_id})

    if res.deleted_count:
        await event.reply("🗑 Removed")
    else:
        await event.reply("⚠️ Not found")


# ========= LIST USERS =========
@bot.on(events.NewMessage(pattern=r"^/users$"))
async def list_users(event):
    if not is_owner(event.sender_id):
        return await event.reply("❌ Not owner")

    users = [u async for u in tracked_col.find({})]

    if not users:
        return await event.reply("No users")

    txt = "\n".join([f"`{u['user_id']}`" for u in users])
    await event.reply(f"Tracked Users:\n{txt}")


# ========= DM LOGGER =========
async def start_dm_logger():
    docs = [s async for s in sessions_col.find({})]

    for s in docs:
        cli = TelegramClient(StringSession(s["string"]), API_ID, API_HASH)

        @cli.on(events.NewMessage(incoming=True))
        async def handler(event):
            if not event.is_private:
                return

            sender = await event.get_sender()
            user_id = sender.id

            # check tracked users
            user = await tracked_col.find_one({"user_id": user_id})
            if not user:
                return

            text = event.message.message or "Non-text"

            msg = f"""
📩 Tracked DM

👤 {sender.first_name}
🆔 {user_id}

💬 {text}
"""

            await send_log(msg)

        try:
            await cli.start()
            print(f"✅ Logger started for {s['tg_id']}")
        except (AuthKeyUnregisteredError, SessionRevokedError):
            await sessions_col.delete_one({"tg_id": s["tg_id"]})
            print("Session removed")
        except Exception as e:
            print("Error:", e)


# ========= MAIN =========
async def main():
    await bot.start(bot_token=BOT_TOKEN)

    await send_log("🚀 Bot Started")

    await start_dm_logger()

    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
