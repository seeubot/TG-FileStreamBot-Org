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
    Generates an HLS stream from a Telegram file using a robust piping method.
    It uses an asyncio queue to buffer the downloaded data, preventing
    `BrokenPipeError` and `flood wait`.
    """
    # Create an asyncio Queue to buffer data between download and FFmpeg
    queue = asyncio.Queue()

    async def download_task():
        """Downloads chunks from Telegram and puts them in the queue."""
        log.info("Starting download task to fill FFmpeg pipe.")
        try:
            async for chunk in client.iter_download(file_info.location, chunk_size=524288):
                await queue.put(chunk)
            await queue.put(None)  # Sentinel value to signal end of stream
            log.info("Download task finished.")
        except asyncio.CancelledError:
            log.info("Download task cancelled.")
            await queue.put(None)
        except Exception as e:
            log.error(f"Error during file download: {e}")
            await queue.put(None)

    # Start the download task in the background
    download_coroutine = download_task()
    
    # FFmpeg command with improved HLS options
    cmd = [
        "ffmpeg", 
        "-i", "pipe:0",  # Read from stdin
        "-c", "copy",
        "-map", "0",
        "-f", "hls",
        "-hls_time", "10",
        "-hls_list_size", "0",
        "-hls_segment_type", "fmp4",
        "-hls_playlist_type", "vod",
        "pipe:1"  # Write to stdout
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    try:
        # Task to feed data from the queue to FFmpeg's stdin
        async def feed_ffmpeg_stdin():
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                try:
                    proc.stdin.write(chunk)
                    await proc.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    log.warning("FFmpeg pipe closed prematurely. Stopping feed.")
                    break
            proc.stdin.close()
            log.info("Finished feeding FFmpeg stdin.")

        feed_task = asyncio.create_task(feed_ffmpeg_stdin())

        # Yield FFmpeg's output directly to the web client
        while not proc.stdout.at_eof():
            yield await proc.stdout.read(8192)
        
        # Ensure the feeding task completes
        await feed_task
        
    except (asyncio.CancelledError, ConnectionResetError):
        log.info("HLS stream generation was cancelled or the client disconnected.")
        proc.terminate()
        
    except Exception as e:
        log.error("An error occurred during HLS stream generation: %s", e, exc_info=True)
    finally:
        if 'proc' in locals() and proc.returncode is None:
            proc.terminate()
        if 'proc' in locals():
            await proc.wait()

