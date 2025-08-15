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
    Generates an HLS stream from a Telegram file by downloading it first,
    which is the most reliable method to avoid FFmpeg streaming errors.
    """
    # Create a temporary file path
    temp_file_path = f"/tmp/{file_info.file_id}_{file_info.file_name}"
    
    try:
        # Step 1: Download the entire file to the temporary path
        log.info(f"Downloading file to temporary path: {temp_file_path}")
        await client.download_media(file_info.location, temp_file_path)
        log.info(f"Download complete.")
        
        # Step 2: Run FFmpeg with the temporary file as input
        cmd = [
            "ffmpeg", "-i", temp_file_path, "-codec", "copy",
            "-map", "0:0", "-f", "hls", "-hls_list_size", "0",
            "-hls_segment_type", "fmp4", "pipe:1"
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Step 3: Read the HLS stream from FFmpeg's stdout and yield it
        while not proc.stdout.at_eof():
            yield await proc.stdout.read(8192)

    except (asyncio.CancelledError, ConnectionResetError):
        log.info("HLS stream generation was cancelled or the client disconnected.")
    except Exception as e:
        log.error("An error occurred during HLS stream generation: %s", e, exc_info=True)
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            log.info(f"Cleaning up temporary file: {temp_file_path}")
            os.remove(temp_file_path)
        
        if 'proc' in locals() and proc.returncode is None:
            proc.terminate()
        
        if 'proc' in locals():
            await proc.wait()

