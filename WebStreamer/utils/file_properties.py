# This file is a part of TG-FileStreamBot
#
# Modifications made by Deekshith SH, 2024-2025
# Copyright (C) 2024-2025 Deekshith SH

import hashlib
import base64
from dataclasses import dataclass
import logging
from typing import Optional
from telethon import TelegramClient

log = logging.getLogger("WebStreamer.utils.file_properties.file-info")

@dataclass
class FileInfo:
    """A dataclass to hold file properties."""
    file_id: int
    file_size: int
    file_name: str
    mime_type: str
    dc_id: int
    location: any

def pack_file(file_name: str, file_size: int, mime_type: str, file_id: int) -> bytes:
    """
    Packs file information into a byte string for hashing.
    """
    return f"{file_name}|{file_size}|{mime_type}|{file_id}".encode()

def get_short_hash(data: bytes) -> str:
    """
    Generates a short, URL-safe hash for the given data.
    """
    hash_object = hashlib.sha1(data)
    hex_digest = hash_object.hexdigest()
    
    # We use URL-safe base64 encoding to make sure the hash can be used in URLs
    encoded_bytes = base64.urlsafe_b64encode(hex_digest.encode('utf-8'))
    
    return encoded_bytes.decode('utf-8')[:8]  # Take a short prefix

async def get_file_info(client: TelegramClient, channel_id: int, message_id: int) -> Optional[FileInfo]:
    """
    Retrieves a file's properties from a Telegram message, handling all media types.
    """
    try:
        message = await client.get_messages(channel_id, ids=message_id)
        if not message:
            log.warning(f"Message with ID {message_id} not found.")
            return None
        
        media = None
        if message.document:
            media = message.document
        elif message.video:
            media = message.video
        elif message.audio:
            media = message.audio
        elif message.photo:
            media = message.photo
        
        if not media:
            log.warning(f"Message with ID {message_id} does not contain a document or other media.")
            return None
            
        file_id = media.id
        file_size = media.size
        
        if hasattr(media, 'mime_type') and media.mime_type:
            mime_type = media.mime_type
        else:
            mime_type = 'application/octet-stream' # Fallback mime type
            
        file_name = getattr(media.attributes[0], 'file_name', 'file') if media.attributes else 'file'
        
        dc_id = media.dc_id
        location = media
        
        return FileInfo(file_id, file_size, file_name, mime_type, dc_id, location)
    
    except Exception as e:
        log.error("An error occurred while getting file info: %s", e, exc_info=True)
        return None


