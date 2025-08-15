# This file is a part of TG-FileStreamBot
#
# Modifications made by Deekshith SH, 2024-2025
# Copyright (C) 2024-2025 Deekshith SH

import logging
import asyncio
from aiohttp import web
from WebStreamer.clients import StreamBot
from WebStreamer.utils.file_properties import get_file_info
from WebStreamer.utils.bot_utils import is_check_hash_match
from WebStreamer.utils.ffmpeg_utils import is_media, is_ffmpeg_installed, get_media_properties, generate_hls_from_stream
from WebStreamer.vars import Var

routes = web.RouteTableDef()
log = logging.getLogger(__name__)

# Corrected routes to include a /stream/ prefix for all streaming endpoints.
@routes.get("/stream/hls/{message_id}.m3u8")
async def hls_stream_handler(request: web.Request):
    """
    Handles HLS streaming requests for media files.
    """
    message_id = request.match_info['message_id']
    if not message_id.isdigit():
        return web.Response(text="Invalid message ID", status=400)
    
    message_id = int(message_id)
    hash_value = request.query.get("hash")

    file_info = await get_file_info(StreamBot, Var.BIN_CHANNEL, message_id)
    if not file_info:
        return web.Response(text="File not found or not a valid document.", status=404)
        
    if not is_check_hash_match(file_info, hash_value):
        return web.Response(text="Hash mismatch. Unauthorized access.", status=401)
        
    if not is_media(file_info.mime_type):
        return web.Response(text="This file is not a media file.", status=400)
    
    if not is_ffmpeg_installed():
        return web.Response(text="FFmpeg is not installed on the server.", status=500)

    try:
        response = web.Response(status=200, content_type="application/x-mpegURL")
        response.headers['Content-Disposition'] = 'inline'
        async def stream_generator():
            try:
                async for chunk in generate_hls_from_stream(StreamBot, file_info):
                    yield chunk
            except asyncio.CancelledError:
                log.info("HLS stream cancelled.")
                raise
            except Exception as e:
                log.error("Error during HLS streaming: %s", e)
        
        response.body = stream_generator()
        return response
        
    except Exception as e:
        log.error("An error occurred during HLS streaming: %s", e)
        return web.Response(text="An error occurred while trying to stream the file.", status=500)

@routes.get("/stream/{message_id}")
async def direct_stream_handler(request: web.Request):
    """
    Handles direct streaming and download requests.
    """
    message_id = request.match_info.get("message_id")
    if not message_id or not message_id.isdigit():
        return web.Response(text="Invalid message ID", status=400)

    message_id = int(message_id)
    hash_value = request.query.get("hash")
    stream_as = request.query.get("s")
    
    file_info = await get_file_info(StreamBot, Var.BIN_CHANNEL, message_id)
    if not file_info:
        return web.Response(text="File not found or not a valid document.", status=404)
        
    if not is_check_hash_match(file_info, hash_value):
        return web.Response(text="Hash mismatch. Unauthorized access.", status=401)

    disposition = "inline" if stream_as else "attachment"
    
    response = web.StreamResponse(status=200, headers={
        "Content-Type": file_info.mime_type,
        "Content-Length": str(file_info.file_size),
        "Content-Disposition": f"{disposition}; filename={file_info.file_name}"
    })
    
    try:
        await response.prepare(request)
        async for chunk in StreamBot.iter_download(file_info.location):
            await response.write(chunk)
            
    except ConnectionResetError:
        log.warning("Connection was reset by the client.")
    except asyncio.CancelledError:
        log.info("Download cancelled.")
    except Exception as e:
        log.error("An unexpected error occurred during streaming: %s", e)
    finally:
        return response

