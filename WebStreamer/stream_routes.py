# This file is a part of TG-FileStreamBot
#
# Modifications made by Deekshith SH, 2024-2025
# Copyright (C) 2024-2025 Deekshith SH

import os
import logging
import asyncio
from aiohttp import web
from WebStreamer.clients import StreamBot
from WebStreamer.utils.file_properties import get_file_info
from WebStreamer.utils.bot_utils import is_check_hash_match
from WebStreamer.utils.ffmpeg_utils import is_media, is_ffmpeg_installed, download_to_file, generate_hls_from_file, generate_direct_stream_from_file
from WebStreamer.vars import Var

routes = web.RouteTableDef()
log = logging.getLogger(__name__)

# Cache for temporary file paths
file_cache = {}

@routes.get("/status", allow_head=True)
async def root_route_handler(_: web.Request):
    return web.json_response(
        {
            "server_status": "running",
            "telegram_bot": "@" + Var.USERNAME,
            "version": "1.0",
        }
    )

@routes.get(r"/hls/{message_id:\d+}.m3u8", allow_head=True)
@routes.get(r"/stream/hls/{message_id:\d+}.m3u8", allow_head=True)
async def hls_stream_handler(request: web.Request):
    message_id = int(request.match_info['message_id'])
    hash_value = request.query.get("hash")
    
    file_info = await get_file_info(StreamBot, Var.BIN_CHANNEL, message_id)
    if not file_info:
        return web.Response(text="File not found or not a valid document.", status=404)
        
    if not is_check_hash_match(file_info, message_id, hash_value):
        return web.Response(text="Hash mismatch. Unauthorized access.", status=401)
        
    if not is_media(file_info.mime_type):
        return web.Response(text="This file is not a media file.", status=400)
    
    if not is_ffmpeg_installed():
        return web.Response(text="FFmpeg is not installed on the server.", status=500)

    temp_file_path = file_cache.get(message_id)
    if not temp_file_path or not os.path.exists(temp_file_path):
        temp_file_path = f"temp_files/{message_id}_{file_info.file_name}"
        if not await download_to_file(StreamBot, file_info, temp_file_path):
            return web.Response(text="An error occurred while downloading the file.", status=500)
        file_cache[message_id] = temp_file_path

    try:
        response = web.Response(status=200, content_type="application/x-mpegURL")
        response.headers['Content-Disposition'] = 'inline'
        
        async def stream_generator():
            async for chunk in generate_hls_from_file(temp_file_path):
                yield chunk
        
        response.body = stream_generator()
        return response
        
    except (ConnectionResetError, asyncio.CancelledError):
        # This means the user disconnected. We can just log this gracefully.
        log.info("Client disconnected during HLS streaming.")
    except Exception as e:
        log.error("An unexpected error occurred during HLS streaming: %s", e)
        return web.Response(text="An error occurred while trying to stream the file.", status=500)

@routes.get(r"/{message_id:\d+}", allow_head=True)
@routes.get(r"/stream/{message_id:\d+}", allow_head=True)
async def direct_stream_handler(request: web.Request):
    message_id = int(request.match_info.get("message_id"))
    hash_value = request.query.get("hash")
    stream_as = request.query.get("s")
    
    file_info = await get_file_info(StreamBot, Var.BIN_CHANNEL, message_id)
    if not file_info:
        return web.Response(text="File not found or not a valid document.", status=404)
        
    if not is_check_hash_match(file_info, message_id, hash_value):
        return web.Response(text="Hash mismatch. Unauthorized access.", status=401)

    temp_file_path = file_cache.get(message_id)
    if not temp_file_path or not os.path.exists(temp_file_path):
        temp_file_path = f"temp_files/{message_id}_{file_info.file_name}"
        if not await download_to_file(StreamBot, file_info, temp_file_path):
            return web.Response(text="An error occurred while downloading the file.", status=500)
        file_cache[message_id] = temp_file_path

    disposition = "inline" if stream_as else "attachment"
    
    response = web.StreamResponse(status=200, headers={
        "Content-Type": file_info.mime_type,
        "Content-Disposition": f"{disposition}; filename={file_info.file_name}"
    })
    
    try:
        await response.prepare(request)
        async for chunk in generate_direct_stream_from_file(temp_file_path):
            await response.write(chunk)
            
    except (ConnectionResetError, asyncio.CancelledError):
        # Client disconnected during streaming.
        log.info("Client disconnected during direct streaming.")
    except Exception as e:
        log.error("An unexpected error occurred during streaming: %s", e)
    finally:
        # It's crucial to finalize the response even on an error
        if not response.started:
            # If the response hasn't even started, we should send an error code.
            # This is a fallback in case of an extremely early error.
            return web.Response(text="An error occurred.", status=500)

