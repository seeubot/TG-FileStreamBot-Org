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
    Robustly streams a file from Telegram and pipes it to an external process (like ffmpeg)
    or directly to the client. This function uses a single, direct pipeline for stability.
    """
    proc = None
    if process_cmd:
        try:
            # Create a subprocess for FFmpeg
            proc = await asyncio.create_subprocess_exec(
                *process_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
        except FileNotFoundError:
            log.error("FFmpeg not found. Is it installed?")
            raise
    
    try:
        async for chunk in client.iter_download(file_info.location, chunk_size=524288):
            if proc:
                try:
                    proc.stdin.write(chunk)
                    await proc.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    log.warning("FFmpeg pipe closed prematurely.")
                    break
            else:
                yield chunk

        if proc:
            proc.stdin.close()
            
            while True:
                chunk = await proc.stdout.read(8192)
                if not chunk:
                    break
                yield chunk
            
            await proc.wait()
            
    except (asyncio.CancelledError, ConnectionResetError):
        log.info("Stream cancelled by client.")
        if proc and proc.returncode is None:
            proc.terminate()
            await proc.wait()
        raise
    except Exception as e:
        log.error(f"Error during streaming: {e}")
    finally:
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

