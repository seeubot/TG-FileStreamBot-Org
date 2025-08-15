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

async def stream_to_process(client: TelegramClient, file_info: FileInfo, process_cmd: list = None):
    """
    Robustly streams a file from Telegram and pipes it to an external process (like ffmpeg).
    This function handles both direct and transcoded streams using an asyncio Queue.
    """
    queue = asyncio.Queue()
    
    # Task 1: Download chunks from Telegram into the queue
    async def download_task():
        try:
            async for chunk in client.iter_download(file_info.location, chunk_size=524288):
                await queue.put(chunk)
            await queue.put(None)  # Sentinel value to signal end of stream
        except asyncio.CancelledError:
            await queue.put(None)
            log.info("Download task cancelled.")
        except Exception as e:
            log.error(f"Error in download task: {e}")
            await queue.put(None)
    
    download_coroutine = asyncio.create_task(download_task())
    
    proc = None
    if process_cmd:
        # Task 2: Create a subprocess for FFmpeg if a command is provided
        proc = await asyncio.create_subprocess_exec(
            *process_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )

    try:
        if proc:
            # Task 3: Feed the downloaded chunks from the queue to FFmpeg's stdin
            async def feed_ffmpeg_stdin():
                while True:
                    chunk = await queue.get()
                    if chunk is None:
                        break
                    try:
                        proc.stdin.write(chunk)
                        await proc.stdin.drain()
                    except (BrokenPipeError, ConnectionResetError):
                        log.warning("FFmpeg pipe closed prematurely.")
                        break
                proc.stdin.close()
            
            feed_task = asyncio.create_task(feed_ffmpeg_stdin())

            # Yield FFmpeg's stdout directly to the client
            while not proc.stdout.at_eof():
                yield await proc.stdout.read(8192)
            
            await feed_task
            await proc.wait()
            
        else:
            # Direct streaming: yield chunks from the queue directly
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
    
    except asyncio.CancelledError:
        log.info("Stream cancelled by client.")
        if proc:
            proc.terminate()
            await proc.wait()
        download_coroutine.cancel()
        raise
    except Exception as e:
        log.error(f"Error during streaming: {e}")
    finally:
        # Ensure cleanup of all tasks and processes
        if download_coroutine and not download_coroutine.done():
            download_coroutine.cancel()
        if proc and proc.returncode is None:
            proc.terminate()
            await proc.wait()

async def generate_hls_from_stream(client: TelegramClient, file_info: FileInfo):
    """
    Generates an HLS stream by piping a Telegram file to FFmpeg.
    """
    cmd = [
        "ffmpeg", "-i", "pipe:0", "-c", "copy", "-map", "0", "-f", "hls", 
        "-hls_time", "10", "-hls_list_size", "0", "-hls_segment_type", "fmp4", 
        "-hls_playlist_type", "vod", "pipe:1"
    ]
    async for chunk in stream_to_process(client, file_info, process_cmd=cmd):
        yield chunk

async def generate_direct_stream(client: TelegramClient, file_info: FileInfo):
    """
    Generates a direct stream from a Telegram file without any transcoding.
    """
    async for chunk in stream_to_process(client, file_info):
        yield chunk

