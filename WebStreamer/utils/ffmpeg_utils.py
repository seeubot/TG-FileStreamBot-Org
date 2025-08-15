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
    Generates an HLS stream from a Telegram file using FFmpeg, piping data directly.
    This version uses a separate task to feed data to FFmpeg's stdin.
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

    async def download_and_feed():
        """Downloads file chunks and feeds them to FFmpeg's stdin."""
        try:
            async for chunk in client.iter_download(file_info.location):
                try:
                    proc.stdin.write(chunk)
                    await proc.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    log.warning("FFmpeg pipe closed prematurely. Stopping download.")
                    break
        except Exception as e:
            log.error(f"Error during file download: {e}")
        finally:
            proc.stdin.close()
            log.info("Finished feeding file to FFmpeg.")

    download_task = asyncio.create_task(download_and_feed())

    try:
        # Yield FFmpeg's output directly to the web client
        while not proc.stdout.at_eof():
            yield await proc.stdout.read(8192)

    except asyncio.CancelledError:
        log.info("HLS stream generation was cancelled by client disconnection.")
        # Clean up both the download task and the FFmpeg process
        download_task.cancel()
        if proc.returncode is None:
            proc.terminate()
        await proc.wait()
        raise
    except Exception as e:
        log.error("An error occurred during HLS stream generation: %s", e, exc_info=True)
    finally:
        # Ensure download task and process are properly terminated
        await download_task
        await proc.wait()

