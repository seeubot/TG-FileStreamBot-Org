# This file is a part of TG-FileStreamBot
#
# Modifications made by Deekshith SH, 2024-2025
# Copyright (C) 2024-2025 Deekshith SH

import logging
import asyncio
import sys
import traceback
from aiohttp import web
from WebStreamer.stream_routes import routes
from WebStreamer.utils.util import load_plugins
from WebStreamer.clients import StreamBot
from WebStreamer.vars import Var

logging.basicConfig(
    level=logging.DEBUG if Var.DEBUG else logging.INFO,
    datefmt="%d/%m/%Y %H:%M:%S",
    format="[%(asctime)s][%(name)s][%(levelname)s] ==> %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)

logging.getLogger("aiohttp").setLevel(logging.ERROR)
logging.getLogger("telethon").setLevel(logging.INFO)

app = web.Application(client_max_size=1024*8) # 8KB
app.add_routes(routes)
server = web.AppRunner(app)

async def start_services():
    logging.info("Initializing Telegram Bot")
    await StreamBot.start(bot_token=Var.BOT_TOKEN)
    bot_info = await StreamBot.get_me()
    Var.USERNAME = bot_info.username
    Var.FIRST_NAME=bot_info.first_name
    logging.info("Initialized Telegram Bot")
    
    logging.info('Importing plugins')
    load_plugins("WebStreamer/plugins")
    logging.info("Imported Plugins")
    
    logging.info("Initializing Web Server")
    await server.setup()
    await web.TCPSite(server, Var.BIND_ADDRESS, Var.PORT).start()
    logging.info("Service Started")
    logging.info("bot =>> %s", Var.FIRST_NAME)
    logging.info("DC ID =>> %s", str(StreamBot.session.dc_id))
    logging.info(" URL =>> %s", Var.URL)
    await StreamBot.run_until_disconnected()

async def main():
    try:
        await start_services()
    except Exception:
        logging.error(traceback.format_exc())
    finally:
        await server.cleanup()
        await StreamBot.disconnect()
        logging.info("Stopped Services")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

