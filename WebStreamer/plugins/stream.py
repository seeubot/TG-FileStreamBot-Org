# This file is a part of TG-FileStreamBot
#
# Modifications made by Deekshith SH, 2024-2025
# Copyright (C) 2024-2025 Deekshith SH

import logging
from telethon import Button, errors
from telethon.events import NewMessage
from WebStreamer.clients import StreamBot
from WebStreamer.utils.file_properties import get_file_info, pack_file, get_short_hash
from WebStreamer.vars import Var
from telethon.extensions import html

MEDIA={"video", "audio"} # we can expand it to include more media types

@StreamBot.on(NewMessage(func=lambda e: e.is_private and e.message.file, forwards=True))
async def media_receive_handler(event: NewMessage.Event):
    """
    Handles incoming file messages in private chats and generates stream links.
    """
    user = await event.get_sender()
    
    logging.info(f"Received a message from user ID: {user.id}")

    if (Var.ALLOWED_USERS and user.id not in Var.ALLOWED_USERS) or (
        Var.BLOCKED_USERS and user.id in Var.BLOCKED_USERS):
        return await event.message.reply(
            message="You are not in the allowed list of users who can use me.",
            link_preview=False,
            parse_mode=html
        )
    
    if not event.message.file:
        return await event.message.reply(
            message="Please send me a file to get a stream link.",
            link_preview=False,
            parse_mode=html
        )
        
    try:
        log_msg=await event.message.forward_to(Var.BIN_CHANNEL)
        
        # FIX: Changed `event.client` to `StreamBot` to use the main bot instance
        file_info=await get_file_info(StreamBot, log_msg.chat_id, log_msg.id)
        
        if not file_info:
            logging.error("Failed to retrieve file info for message ID: %s", log_msg.id)
            return await event.message.reply("Sorry, I could not get file info for this message.")

        full_hash = pack_file(
            file_info.file_name,
            file_info.file_size,
            file_info.mime_type,
            file_info.file_id
        )
        file_hash=get_short_hash(full_hash)
        
        stream_link = f"{Var.URL}stream/{log_msg.id}?hash={file_hash}"
        hls_stream_link = f"{Var.URL}hls/{log_msg.id}.m3u8?hash={file_hash}"
        
        is_media = bool(set(file_info.mime_type.split("/")) & MEDIA)
        
        buttons=[[Button.url("Open", url=stream_link)]]
        message = f"<code>{stream_link}</code>"
        
        if is_media:
            buttons.append([Button.url("Stream", url=stream_link+"&s=1")])
            buttons.append([Button.url("HLS Stream", url=hls_stream_link)])
            message+=f"\n\n<a href='{stream_link}&s=1'>(Stream)</a>"
            message+=f"\n<a href='{hls_stream_link}'>(HLS Stream)</a>"
            
        await event.message.reply(
            message=message,
            link_preview=False,
            buttons=buttons,
            parse_mode=html
        )
    except errors.FloodWaitError as e:
        logging.error("FloodWaitError: %s", e)
    except Exception as e:
        logging.error("An unexpected error occurred: %s", e, exc_info=True)
        await event.message.reply("An unexpected error occurred while processing your request. Please try again.")

