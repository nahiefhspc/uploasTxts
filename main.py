import asyncio
import aiohttp
import logging
from telegram import Bot
from telegram.ext import Application
from pymongo import MongoClient
from datetime import datetime, timedelta
import pytz

BOT_TOKEN = "6223059105:AAGgaB0BRIGfec1cYTbaQyr6uy4ragjNWt0" 
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJleHAiOjE3NDYzMzkwMzkuMDQ0LCJkYXRhIjp7Il9pZCI6IjY0YjY0NDhkNjAxYWM2MDAxOGQ5ODE1MyIsInVzZXJuYW1lIjoiOTM1MjYzMTczMSIsImZpcnN0TmFtZSI6Ik5hbWFuIiwibGFzdE5hbWUiOiIiLCJvcmdhbml6YXRpb24iOnsiX2lkIjoiNWViMzkzZWU5NWZhYjc0NjhhNzlkMTg5Iiwid2Vic2l0ZSI6InBoeXNpY3N3YWxsYWguY29tIiwibmFtZSI6IlBoeXNpY3N3YWxsYWgifSwiZW1haWwiOiJvcG1hc3Rlcjk4NTRAZ21haWwuY29tIiwicm9sZXMiOlsiNWIyN2JkOTY1ODQyZjk1MGE3NzhjNmVmIl0sImNvdW50cnlHcm91cCI6IklOIiwidHlwZSI6IlVTRVIifSwiaWF0IjoxNzQ1NzM0MjM5fQ.GNUr2USwCUeV7Y8gWsyIp3yuGnaSdrg7bbjkCBSdguI"
MONGO_URI = "mongodb+srv://namanjain123eudhc:opmaster@cluster0.5iokvxo.mongodb.net/?retryWrites=true&w=majority"  # Replace with your MongoDB connection string
# Mapping of batch IDs to channel IDs
BATCH_CHANNEL_MAP = {
    "67738e4a5787b05d8ec6e07f": "-1002539689928",  # Replace with your batch ID and channel ID       # Add more batch-channel pairs as needed
}

# MongoDB client
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["content_db"]

HEADERS = {
    'Host': 'api.penpencil.co',
    'client-id': '5eb393ee95fab7468a79d189',
    'client-version': '1910',
    'user-agent': 'Mozilla/5.0',
    'randomid': '72012511-256c-4e1c-b4c7-29d67136af37',
    'client-type': 'WEB',
    'content-type': 'application/json; charset=utf-8',
    'authorization': f"Bearer {ACCESS_TOKEN}",
}

logging.basicConfig(level=logging.INFO)

async def fetch_json(session, url):
    async with session.get(url, headers=HEADERS) as response:
        if response.status == 200:
            return await response.json()
        return None

async def get_content_details(session, batch_id, subject_id, schedule_id):
    url = f"https://api.penpencil.co/v1/batches/{batch_id}/subject/{subject_id}/schedule/{schedule_id}/schedule-details"
    data = await fetch_json(session, url)
    content = set()

    if data and data.get("success") and data.get("data"):
        item = data["data"]
        video = item.get('videoDetails', {})
        if video:
            name = item.get('topic')
            url = video.get('videoUrl') or video.get('embedCode')
            if name and url:
                content.add((name, url))
        for hw in item.get('homeworkIds', []):
            for att in hw.get('attachmentIds', []):
                url = att.get('baseUrl', '') + att.get('key', '')
                name = hw.get('topic')
                if name and url:
                    content.add((name, url))
        dpp = item.get('dpp')
        if dpp:
            for hw in dpp.get('homeworkIds', []):
                for att in hw.get('attachmentIds', []):
                    url = att.get('baseUrl', '') + att.get('key', '')
                    name = hw.get('topic')
                    if name and url:
                        content.add((name, url))
    return list(content)

async def get_today_content(session, batch_id):
    url = f"https://api.penpencil.co/v1/batches/{batch_id}/todays-schedule"
    data = await fetch_json(session, url)
    all_content = set()

    if data and data.get("success") and data.get("data"):
        tasks = []
        for item in data['data']:
            sid = item.get('_id')
            subid = item.get('batchSubjectId')
            tasks.append(get_content_details(session, batch_id, subid, sid))
        results = await asyncio.gather(*tasks)
        for res in results:
            all_content.update(res)
    return list(all_content)

async def is_new_content(batch_id, url):
    collection = db[f"batch_{batch_id}"]
    return collection.find_one({"url": url}) is None

async def save_content(batch_id, name, url):
    collection = db[f"batch_{batch_id}"]
    collection.insert_one({
        "name": name,
        "url": url,
        "timestamp": datetime.utcnow()
    })

async def clear_batch_data(batch_id):
    while True:
        try:
            # Get current time in UTC
            now = datetime.now(pytz.UTC)
            # Calculate time until 11 PM today (or tomorrow if past 11 PM)
            target_time = now.replace(hour=23, minute=30, second=0, microsecond=0)
            if now.hour >= 23:
                target_time += timedelta(days=1)
            seconds_until_11pm = (target_time - now).total_seconds()
            
            # Wait until 11 PM
            await asyncio.sleep(seconds_until_11pm)
            
            # Clear the batch's collection
            collection = db[f"batch_{batch_id}"]
            collection.delete_many({})
            logging.info(f"Cleared data for batch {batch_id} at 11 PM")
            
            # Sleep for 1 minute to avoid immediate re-trigger
            await asyncio.sleep(60)
        except Exception as e:
            logging.error(f"Error clearing data for batch {batch_id}: {e}")
            await asyncio.sleep(60)

async def monitor_batch(bot, batch_id, channel_id):
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                content = await get_today_content(session, batch_id)
                new_items = []
                
                # Check which items are new based on URL only
                for name, url in content:
                    if await is_new_content(batch_id, url):
                        new_items.append((name, url))

                if new_items:
                    for i, (name, url) in enumerate(new_items):
                        # Send to channel
                        message = f"{name}: {url}"
                        await bot.send_message(chat_id=channel_id, text=message)
                        # Save to database
                        await save_content(batch_id, name, url)
                        # Add 120-second delay if more than one item and not the last item
                        if len(new_items) > 1 and i < len(new_items) - 1:
                            await asyncio.sleep(120)
                await asyncio.sleep(300)  # Check every 5 minutes
            except Exception as e:
                logging.error(f"Monitor error for batch {batch_id}: {e}")
                await asyncio.sleep(60)

async def start_monitoring(application):
    bot = application.bot
    tasks = []
    for batch_id, channel_id in BATCH_CHANNEL_MAP.items():
        # Start monitoring task for each batch
        tasks.append(monitor_batch(bot, batch_id, channel_id))
        # Start cleanup task for each batch
        tasks.append(clear_batch_data(batch_id))
    await asyncio.gather(*tasks)

async def main():
    application = Application.builder().token(BOT_TOKEN).build()
    await application.initialize()
    await application.start()
    print("Bot is running...")
    asyncio.create_task(start_monitoring(application))
    await application.updater.start_polling()

# Fix for Pydroid 3 – manually create and set event loop
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
try:
    loop.run_until_complete(main())
    loop.run_forever()
finally:
    mongo_client.close()  # Ensure MongoDB connection is closed on exit
