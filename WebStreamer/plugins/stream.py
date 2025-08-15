# This file is a part of TG-FileStreamBot
# pylint: disable=relative-beyond-top-level

import logging
from telethon import Button, errors
from telethon.events import NewMessage
from telethon.extensions import html
from WebStreamer.clients import StreamBot
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
        
        file_info = await get_file_info(StreamBot, log_msg.chat_id, log_msg.id)

        full_hash = pack_file(
            file_info.file_name,
            file_info.file_size,
            file_info.mime_type,
            log_msg.id  # Use the message ID as the unique file identifier
        )
        file_hash=get_short_hash(full_hash)
        
        stream_link = f"{Var.URL}stream/{log_msg.id}?hash={file_hash}"
        hls_link = f"{Var.URL}hls/{log_msg.id}.m3u8?hash={file_hash}"
        
        is_media = bool(set(file_info.mime_type.split("/")) & MEDIA)
        buttons=[[Button.url("Open", url=stream_link)]]
        message = f"<code>{stream_link}</code>"
        
        if is_media:
            buttons.append([Button.url("HLS Stream", url=hls_link)])
            message+=f"\n\n<b>HLS Stream:</b> <code>{hls_link}</code>"
            
        await event.message.reply(
            message=message,
            link_preview=False,
            buttons=buttons,
            parse_mode=html
        )
    except errors.FloodWaitError as e:
        logging.error(e)

