import asyncio
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import AuthKeyUnregisteredError, SessionRevokedError
from motor.motor_asyncio import AsyncIOMotorClient

# ✅ CONFIG
from config import *

# ========= MONGO =========
mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo["ManagerBot"]

sessions_col = db["sessions"]
tracked_col = db["tracked_users"]

# 👉 reply mapping DB (permanent)
map_col = db["message_map"]

# ========= BOT =========
bot = TelegramClient("manager-bot", API_ID, API_HASH)

# ========= HELPERS =========
def is_owner(uid):
    return int(uid) in [int(x) for x in OWNER_IDS]


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

    sess = event.pattern_match.group(1).strip()
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


# ========= DM LOGGER =========
async def start_dm_logger():
    docs = [s async for s in sessions_col.find({})]

    for s in docs:
        try:
            cli = TelegramClient(StringSession(s["string"]), API_ID, API_HASH)
            await cli.start()

            print(f"✅ Logger started for {s['tg_id']}")

            async def handler(event, client=cli):
                if not event.is_private:
                    return

                sender = await event.get_sender()
                user_id = sender.id

                # check tracked users
                user = await tracked_col.find_one({"user_id": user_id})
                if not user:
                    return

                # forward message
                fwd = await event.forward_to(LOGGER_ID)

                # save mapping in DB
                await map_col.insert_one({
                    "logger_msg_id": fwd.id,
                    "user_id": user_id,
                    "session": s["string"]
                })

                info = f"""
📩 Tracked DM

👤 {sender.first_name}
🆔 {user_id}
"""
                await send_log(info)

            cli.add_event_handler(handler, events.NewMessage(incoming=True))

        except (AuthKeyUnregisteredError, SessionRevokedError):
            await sessions_col.delete_one({"tg_id": s["tg_id"]})
            print(f"❌ Removed dead session {s['tg_id']}")

        except Exception as e:
            print("Error:", e)


# ========= REPLY SYSTEM =========
@bot.on(events.NewMessage(chats=LOGGER_ID))
async def reply_handler(event):

    if not event.is_reply:
        return

    reply = await event.get_reply_message()

    data = await map_col.find_one({"logger_msg_id": reply.id})

    if not data:
        return

    user_id = data["user_id"]
    session = data["session"]

    try:
        cli = TelegramClient(StringSession(session), API_ID, API_HASH)
        await cli.start()

        if event.message.media:
            await cli.send_file(
                user_id,
                event.message.media,
                caption=event.message.text or ""
            )
        else:
            await cli.send_message(user_id, event.message.message)

        await event.reply("✅ Reply sent")

        await cli.disconnect()

    except Exception as e:
        await event.reply(f"❌ Error: {e}")


# ========= MAIN =========
async def main():
    await bot.start(bot_token=BOT_TOKEN)

    print("🚀 Bot Started")

    await start_dm_logger()

    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
