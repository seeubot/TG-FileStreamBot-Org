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

def is_ffmpeg_installed():
    """Checks if FFmpeg is installed on the system."""
    return os.path.exists("/usr/bin/ffmpeg")

def is_media(mime_type: str) -> bool:
    """Checks if the mime type is a recognized media type."""
    return "video/" in mime_type or "audio/" in mime_type

async def download_to_file(client: TelegramClient, file_info: FileInfo, temp_file_path: str):
    """Downloads a file from Telegram to a local temporary file."""
    try:
        log.info(f"Downloading file to {temp_file_path}")
        await client.download_media(file_info.location, temp_file_path)
        log.info(f"Download complete for {file_info.file_name}")
        return True
    except asyncio.CancelledError:
        log.info("Download task cancelled.")
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise
    except Exception as e:
        log.error(f"Error downloading file: {e}")
        return False

async def generate_hls_from_file(file_path: str):
    """
    Generates an HLS stream by piping a local file to FFmpeg.
    """
    cmd = [
        "ffmpeg", "-i", file_path, "-c", "copy", "-map", "0", "-f", "hls", 
        "-hls_time", "10", "-hls_list_size", "0", "-hls_segment_type", "fmp4", 
        "-hls_playlist_type", "vod", "pipe:1"
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL
    )
    
    while True:
        chunk = await proc.stdout.read(8192)
        if not chunk:
            break
        yield chunk
    
    await proc.wait()

async def generate_direct_stream_from_file(file_path: str):
    """
    Generates a direct stream from a local file.
    """
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            yield chunk


