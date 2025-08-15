# This file is a part of TG-FileStreamBot
# pylint: disable=relative-beyond-top-level

import logging
from telethon import Button, errors
from telethon.events import NewMessage
from telethon.extensions import html
from WebStreamer.clients import StreamBot
# We import get_file_info, pack_file, and get_short_hash from our utility file.
# The get_file_info function is a wrapper for get_file_ids.
from WebStreamer.utils.file_properties import get_file_info, pack_file, get_short_hash
from WebStreamer.vars import Var

MEDIA={"video", "audio"} # we can expand it to include more media types

@StreamBot.on(NewMessage(func=lambda e: True if e.message.file and e.is_private else False))
async def media_receive_handler(event: NewMessage.Event):
    user = await event.get_sender()
    if (Var.ALLOWED_USERS and user.id not in Var.ALLOWED_USERS) or (
        Var.BLOCKED_USERS and user.id in Var.BLOCKED_USERS):
        return await event.message.reply(
            message="You are not in the allowed list of users who can use me.",
            link_preview=False,
            parse_mode=html
        )
    try:
        log_msg=await event.message.forward_to(Var.BIN_CHANNEL)
        # Fix: We must use the 'await' keyword to get the result of the async function.
        file_info=await get_file_info(log_msg)
        full_hash = pack_file(
            file_info.file_name,
            file_info.file_size,
            file_info.mime_type,
            file_info.id
        )
        file_hash=get_short_hash(full_hash)
        
        # The original stream link for direct download
        stream_link = f"{Var.URL}stream/{log_msg.id}?hash={file_hash}"
        
        # The new HLS stream link
        hls_stream_link = f"{Var.URL}hls/{log_msg.id}.m3u8?hash={file_hash}"
        
        is_media = bool(set(file_info.mime_type.split("/")) & MEDIA)
        
        buttons=[[Button.url("Open", url=stream_link)]]
        message = f"<code>{stream_link}</code>"
        
        if is_media:
            # Add buttons for streaming and HLS
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
        logging.error(e)

