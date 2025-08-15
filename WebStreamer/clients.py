# This file is a part of TG-FileStreamBot
#
# Modifications made by Deekshith SH, 2024-2025
# Copyright (C) 2024-2025 Deekshith SH

import logging
from WebStreamer.vars import Var
from telethon import TelegramClient
from telethon.sessions import StringSession

root_log = logging.getLogger(__name__)

# Initialize StreamBot as a single client.
# We no longer need the multi-client dictionary or the complex initialization logic.
StreamBot = TelegramClient(StringSession(), Var.API_ID, Var.API_HASH, app_version="1.0")

if not Var.API_ID or not Var.API_HASH or not Var.BOT_TOKEN:
    root_log.error("API_ID, API_HASH, or BOT_TOKEN is missing. Please check your environment variables.")

# The rest of the functions like initialize_clients are no longer needed.

