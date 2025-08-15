# This file is a part of TG-FileStreamBot
#
# Modifications made by Deekshith SH, 2024-2025
# Copyright (C) 2024-2025 Deekshith SH

import os
import asyncio
import logging
from telethon import TelegramClient
from WebStreamer.utils.file_properties import FileInfo

log = logging.getLogger(__name__)

# This is a very basic check for a unix-like environment
def is_ffmpeg_installed():
    """Checks if FFmpeg is installed on the system."""
    return os.path.exists("/usr/bin/ffmpeg")

def is_media(mime_type: str) -> bool:
    """Checks if the mime type is a recognized media type."""
    return "video/" in mime_type or "audio/" in mime_type

async def get_media_properties(client: TelegramClient, channel_id: int, message_id: int):
    """
    Retrieves media properties like duration and size from a message.
    """
    try:
        message = await client.get_messages(channel_id, ids=message_id)
        if message and message.media:
            return message.media.document
    except Exception as e:
        log.error("Failed to get media properties: %s", e)
    return None


async def generate_hls_from_stream(client: TelegramClient, file_info: FileInfo):
    """
    Generates an HLS stream from a Telegram file using FFmpeg.
    This function now takes the file_info object as an argument.
    """
    cmd = [
        "ffmpeg", "-i", "pipe:0", "-codec", "copy",
        "-map", "0:0", "-f", "hls", "-hls_list_size", "0",
        "-hls_segment_type", "fmp4", "pipe:1"
    ]
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    try:
        # Corrected iter_download call to use the file's location object
        async for chunk in client.iter_download(file_info.location):
            try:
                proc.stdin.write(chunk)
                await proc.stdin.drain()
            except ConnectionError:
                break
        
        proc.stdin.close()
        await proc.stdin.wait_closed()
        
        while not proc.stdout.at_eof():
            yield await proc.stdout.read(8192)

    except (asyncio.CancelledError, ConnectionResetError):
        log.info("HLS stream generation was cancelled or the client disconnected.")
    except Exception as e:
        log.error("An error occurred during HLS stream generation: %s", e, exc_info=True)
    finally:
        if proc.returncode is None:
            proc.terminate()
        await proc.wait()

