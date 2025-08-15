# This file is a part of TG-FileStreamBot
#
# Modifications made by Deekshith SH, 2024-2025
# Copyright (C) 2024-2025 Deekshith SH

import logging
from telethon import Button
from telethon.events import NewMessage
from WebStreamer.clients import StreamBot
from WebStreamer.vars import Var
from telethon.extensions import html

@StreamBot.on(NewMessage(pattern="/start", func=lambda e: e.is_private))
async def start_command_handler(event: NewMessage.Event):
    """
    Handles the /start command. This is a basic diagnostic command to check if the bot is responsive.
    """
    user = await event.get_sender()
    if (Var.ALLOWED_USERS and user.id not in Var.ALLOWED_USERS) or (
        Var.BLOCKED_USERS and user.id in Var.BLOCKED_USERS):
        return await event.message.reply(
            message="You are not in the allowed list of users who can use me.",
            link_preview=False,
            parse_mode=html
        )

    # Log that the start command was received. This helps with debugging.
    logging.info(f"Start command received from user ID: {user.id}")

    # Respond with a welcome message and instructions.
    welcome_message = (
        "👋 Hello there! I'm your Telegram File Streamer Bot.\n\n"
        "Just send or forward me a file, and I will generate a direct "
        "streaming link for it.\n\n"
        "Feel free to test my functionality! "
    )

    buttons = [[
        Button.url("Support", url="https://t.me/your_support_channel"), # Replace with your support channel URL
        Button.url("Source Code", url="https://github.com/your_github_repo") # Replace with your GitHub repo URL
    ]]

    await event.message.reply(
        message=welcome_message,
        link_preview=False,
        buttons=buttons,
        parse_mode=html
    )

