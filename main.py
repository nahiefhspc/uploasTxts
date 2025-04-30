import asyncio
import aiohttp
import logging
from telegram import Bot
from telegram.ext import Application

BOT_TOKEN = "6223059105:AAGgaB0BRIGfec1cYTbaQyr6uy4ragjNWt0" 
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJleHAiOjE3NDYzMzkwMzkuMDQ0LCJkYXRhIjp7Il9pZCI6IjY0YjY0NDhkNjAxYWM2MDAxOGQ5ODE1MyIsInVzZXJuYW1lIjoiOTM1MjYzMTczMSIsImZpcnN0TmFtZSI6Ik5hbWFuIiwibGFzdE5hbWUiOiIiLCJvcmdhbml6YXRpb24iOnsiX2lkIjoiNWViMzkzZWU5NWZhYjc0NjhhNzlkMTg5Iiwid2Vic2l0ZSI6InBoeXNpY3N3YWxsYWguY29tIiwibmFtZSI6IlBoeXNpY3N3YWxsYWgifSwiZW1haWwiOiJvcG1hc3Rlcjk4NTRAZ21haWwuY29tIiwicm9sZXMiOlsiNWIyN2JkOTY1ODQyZjk1MGE3NzhjNmVmIl0sImNvdW50cnlHcm91cCI6IklOIiwidHlwZSI6IlVTRVIifSwiaWF0IjoxNzQ1NzM0MjM5fQ.GNUr2USwCUeV7Y8gWsyIp3yuGnaSdrg7bbjkCBSdguI"

# Mapping of batch IDs to channel IDs
BATCH_CHANNEL_MAP = {
    "67738e4a5787b05d8ec6e07f": "-1002472817328",  # Replace with your batch ID and channel ID         # Add more batch-channel pairs as needed
}

# Per-batch seen items to track unique content
seen_items = {batch_id: set() for batch_id in BATCH_CHANNEL_MAP}

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

async def monitor_batch(bot, batch_id, channel_id):
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                content = await get_today_content(session, batch_id)
                new_items = [(name, url) for name, url in content if (name, url) not in seen_items[batch_id]]

                if new_items:
                    for i, (name, url) in enumerate(new_items):
                        seen_items[batch_id].add((name, url))
                        message = f"{name}: {url}"
                        await bot.send_message(chat_id=channel_id, text=message)
                        # Add 120-second delay if more than one item and not the last item
                        if len(new_items) > 1 and i < len(new_items) - 1:
                            await asyncio.sleep(120)
                await asyncio.sleep(300)  # Check every 5 minutes
            except Exception as e:
                logging.error(f"Monitor error for batch {batch_id}: {e}")
                await asyncio.sleep(60)

async def start_monitoring(application):
    bot = application.bot
    tasks = [
        monitor_batch(bot, batch_id, channel_id)
        for batch_id, channel_id in BATCH_CHANNEL_MAP.items()
    ]
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
loop.run_until_complete(main())
loop.run_forever()
