# Modified stream_routes.py to support HLS streaming in addition to direct download.
# This version implements video processing with FFmpeg.

import time
import logging
import mimetypes
import asyncio
import tempfile
import json
from aiohttp import web
from aiohttp.http_exceptions import BadStatusLine
from WebStreamer.clients import multi_clients, work_loads
from WebStreamer.utils.file_properties import get_short_hash, pack_file, FileInfo
from WebStreamer.utils.util import allow_request, get_requester_ip, get_readable_time
from WebStreamer.vars import Var
from WebStreamer import StartTime, __version__
from WebStreamer.clients import ParallelTransferrer
from typing import Optional

routes = web.RouteTableDef()
class_cache = {}

async def get_video_metadata(file_id: FileInfo, transfer: ParallelTransferrer) -> dict:
    """
    Gets video metadata (duration, etc.) by using ffprobe. This function now
    handles the FileNotFoundError more gracefully, which is the most common
    issue on minimal deployment environments.
    """
    log = logging.getLogger(__name__).getChild("get_video_metadata")
    
    try:
        log.info("Starting ffprobe to get video metadata for file ID %s", file_id.file_id)
        
        with tempfile.NamedTemporaryFile(suffix=file_id.file_name) as temp_file:
            partial_file_data_generator = transfer.download(
                file_id, file_id.file_size, 0, 1024 * 1024, 0, "127.0.0.1"
            )
            async for chunk in partial_file_data_generator:
                temp_file.write(chunk)
            temp_file.flush()

            command = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration,size',
                '-of', 'json',
                '-i', temp_file.name
            ]
            
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                metadata = json.loads(stdout.decode())
                duration_seconds = float(metadata['format']['duration'])
                log.info("ffprobe successful. Duration: %s seconds", duration_seconds)
                return {
                    "duration_seconds": duration_seconds,
                    "segment_duration": 5
                }
            else:
                log.error(f"ffprobe failed with error: {stderr.decode()}")
                return {"duration_seconds": 60, "segment_duration": 5}
                
    except FileNotFoundError:
        log.critical("Error running ffprobe: FFmpeg is not installed or not in PATH.")
        log.critical("HLS streaming functionality will not work until FFmpeg is installed.")
        return {"duration_seconds": 60, "segment_duration": 5}
    except Exception as e:
        log.critical(f"An error occurred during ffprobe processing: {e}", exc_info=True)
        return {"duration_seconds": 60, "segment_duration": 5}

async def create_hls_playlist(request: web.Request, file_id: FileInfo, secure_hash: str) -> str:
    """
    Generates an M3U8 playlist for HLS streaming.
    """
    index = min(work_loads, key=work_loads.get)
    faster_client = multi_clients[index]
    transfer = class_cache.get(faster_client) or ParallelTransferrer(faster_client)
    
    metadata = await get_video_metadata(file_id, transfer)
    duration_seconds = metadata.get("duration_seconds", 60)
    segment_duration = metadata.get("segment_duration", 5)
    
    num_segments = int(duration_seconds / segment_duration)

    playlist = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{segment_duration}",
        "#EXT-X-PLAYLIST-TYPE:VOD",
        f'#EXT-X-MEDIA-SEQUENCE:0',
    ]

    for i in range(num_segments):
        playlist.append(f"#EXTINF:{segment_duration}.0,")
        playlist.append(f"/hls/{file_id.file_id}/{i}.ts?hash={secure_hash}")

    playlist.append("#EXT-X-ENDLIST")
    return "\n".join(playlist)


async def get_video_segment(request: web.Request, file_id: FileInfo, segment_index: int) -> Optional[bytes]:
    """
    Serves a specific video segment by using FFmpeg to extract it from the stream.
    """
    log = logging.getLogger(__name__).getChild("get_video_segment")
    try:
        segment_duration = 5
        start_time_seconds = segment_index * segment_duration
        
        index = min(work_loads, key=work_loads.get)
        faster_client = multi_clients[index]
        transfer = class_cache.get(faster_client) or ParallelTransferrer(faster_client)

        log.info("Starting FFmpeg to extract segment %s for file ID %s", segment_index, file_id.file_id)
        
        command = [
            'ffmpeg',
            '-ss', str(start_time_seconds),
            '-i', 'pipe:0',
            '-t', str(segment_duration),
            '-c', 'copy',
            '-f', 'mpegts',
            'pipe:1'
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        full_file_data_generator = transfer.download(
            file_id, file_id.file_size, 0, file_id.file_size - 1, index, get_requester_ip(request)
        )
        
        try:
            async for chunk in full_file_data_generator:
                process.stdin.write(chunk)
            await process.stdin.drain()
            process.stdin.close()
        except (ConnectionResetError, BrokenPipeError):
            log.warning("Failed to pipe data to FFmpeg, process likely exited early.")
            process.kill()
            await process.wait()
            return None

        segment_data, stderr_data = await process.communicate()
        
        if process.returncode != 0:
            log.error(f"FFmpeg failed with error: {stderr_data.decode()}")
            return None

        return segment_data
    
    except FileNotFoundError:
        log.critical("Error running FFmpeg: The 'ffmpeg' command was not found.")
        log.critical("HLS streaming functionality is disabled.")
        return None
    except Exception as e:
        log.critical(f"An error occurred during FFmpeg processing: {e}", exc_info=True)
        return None

@routes.get("/status", allow_head=True)
async def root_route_handler(_: web.Request):
    return web.json_response(
        {
            "server_status": "running",
            "uptime": get_readable_time(time.time() - StartTime),
            "telegram_bot": "@" + Var.USERNAME,
            "connected_bots": len(multi_clients),
            "loads": dict(
                (f"bot{c + 1}", l)
                for c, l in (
                    sorted(work_loads.items())
                )
            ),
            "version": __version__,
        }
    )

@routes.get(r"/hls/{messageID:\d+}.m3u8", allow_head=True)
async def hls_playlist_handler(request: web.Request):
    try:
        message_id_str = request.match_info["messageID"]
        message_id = int(message_id_str)
        secure_hash = request.rel_url.query.get("hash")
        
        index = min(work_loads, key=work_loads.get)
        faster_client = multi_clients[index]
        transfer = class_cache.get(faster_client) or ParallelTransferrer(faster_client)

        file_id = await transfer.get_file_properties(message_id)
        if not file_id:
            logging.error("File not found for message ID: %s", message_id_str)
            return web.Response(status=404, text="File not found")

        full_hash = pack_file(
            file_id.file_name,
            file_id.file_size,
            file_id.mime_type,
            file_id.id
        )
        if get_short_hash(full_hash) != secure_hash:
            return web.HTTPForbidden(text="Invalid hash")

        playlist_content = await create_hls_playlist(request, file_id, secure_hash)

        return web.Response(
            status=200,
            text=playlist_content,
            headers={
                "Content-Type": "application/x-mpegURL",
                "Content-Disposition": "inline"
            }
        )
    except (AttributeError, BadStatusLine, ConnectionResetError):
        pass
    except Exception as e:
        logging.critical(str(e), exc_info=True)
        raise web.HTTPInternalServerError(text=str(e))


@routes.get(r"/hls/{messageID:\d+}/{segment:\d+}.ts", allow_head=True)
async def hls_segment_handler(request: web.Request):
    try:
        message_id_str = request.match_info["messageID"]
        message_id = int(message_id_str)
        segment_index = int(request.match_info["segment"])
        secure_hash = request.rel_url.query.get("hash")

        index = min(work_loads, key=work_loads.get)
        faster_client = multi_clients[index]
        transfer = class_cache.get(faster_client) or ParallelTransferrer(faster_client)

        file_id = await transfer.get_file_properties(message_id)
        if not file_id:
            logging.error("File not found for message ID: %s", message_id_str)
            return web.Response(status=404, text="File not found")

        full_hash = pack_file(
            file_id.file_name,
            file_id.file_size,
            file_id.mime_type,
            file_id.id
        )
        if get_short_hash(full_hash) != secure_hash:
            return web.HTTPForbidden(text="Invalid hash")

        segment_data = await get_video_segment(request, file_id, segment_index)
        
        if segment_data:
            return web.Response(
                status=200,
                body=segment_data,
                headers={"Content-Type": "video/MP2T"}
            )
        else:
            return web.Response(status=500, text="Failed to generate video segment.")

    except (AttributeError, BadStatusLine, ConnectionResetError):
        pass
    except Exception as e:
        logging.critical(str(e), exc_info=True)
        raise web.HTTPInternalServerError(text=str(e))


@routes.get(r"/stream/{messageID:\d+}", allow_head=True)
async def stream_handler(request: web.Request):
    try:
        message_id = int(request.match_info["messageID"])
        secure_hash = request.rel_url.query.get("hash")
        return await media_streamer(request, message_id, secure_hash)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        pass
    except Exception as e:
        logging.critical(str(e), exc_info=True)
        raise web.HTTPInternalServerError(text=str(e))


async def media_streamer(request: web.Request, message_id: int, secure_hash: str):
    head: bool = request.method == "HEAD"
    ip = get_requester_ip(request)
    range_header = request.headers.get("Range", 0)

    index = min(work_loads, key=work_loads.get)
    faster_client = multi_clients[index]

    if Var.MULTI_CLIENT:
        logging.debug("Client %s is now serving %s", index, ip)

    if faster_client in class_cache:
        transfer = class_cache[faster_client]
        logging.debug("Using cached ByteStreamer object for client %s", index)
    else:
        logging.debug("Creating new ByteStreamer object for client %s", index)
        transfer = ParallelTransferrer(faster_client)
        transfer.post_init()
        class_cache[faster_client] = transfer
        logging.debug("Created new ByteStreamer object for client %s", index)

    file_id = await transfer.get_file_properties(message_id)
    if not file_id:
        return web.Response(status=404, text="File not found")

    full_hash = pack_file(
        file_id.file_name,
        file_id.file_size,
        file_id.mime_type,
        file_id.id
    )
    if get_short_hash(full_hash) != secure_hash:
        logging.debug("Invalid hash for message with ID %s", message_id)
        return web.HTTPForbidden(text="Invalid hash")

    file_size = file_id.file_size

    if range_header:
        from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
        from_bytes = int(from_bytes)
        until_bytes = int(until_bytes) if until_bytes else file_size - 1
    else:
        from_bytes = request.http_range.start or 0
        until_bytes = (request.http_range.stop or file_size) - 1

    if (until_bytes > file_size) or (from_bytes < 0) or (until_bytes < from_bytes):
        return web.Response(
            status=416,
            body="416: Range not satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"},
        )
    until_bytes = min(until_bytes, file_size - 1)
    req_length = until_bytes - from_bytes + 1
    if not head:
        if not allow_request(ip):
            return web.Response(status=429)
        body = transfer.download(
            file_id, file_size, from_bytes, until_bytes, index, ip
        )
    else:
        body = None

    mime_type = file_id.mime_type
    file_name = file_id.file_name
    
    disposition = "inline"
    if not request.rel_url.query.get("s"):
        disposition = "attachment"

    if not mime_type:
        mime_type = mimetypes.guess_type(
            file_name)[0] or "application/octet-stream"
    
    return web.Response(
        status=206 if range_header else 200,
        body=body,
        headers={
            "Content-Type": f"{mime_type}",
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Length": str(req_length),
            "Content-Disposition": f'{disposition}; filename="{file_name}"',
            "Accept-Ranges": "bytes",
        },
    )

