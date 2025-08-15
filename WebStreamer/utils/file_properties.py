# This file is a part of TG-FileStreamBot
#
# Modifications made by Deekshith SH, 2024-2025
# Copyright (C) 2024-2025 Deekshith SH

# pylint: disable=protected-access

import logging
import hashlib
import base64
import json
from dataclasses import dataclass
from typing import Optional
from telethon import TelegramClient
from telethon.tl.types import Message, Document
from telethon.errors import MessageIdInvalidError
from WebStreamer.vars import Var

root_log = logging.getLogger(__name__)

@dataclass
class FileInfo:
    file_id: str
    dc_id: int
    file_size: int
    file_name: str
    mime_type: str
    location: Document

def get_short_hash(data: str) -> str:
    """
    Generates a URL-safe short hash from a string.
    """
    md5_hash = hashlib.md5(data.encode()).hexdigest()
    # Use URL-safe base64 encoding to make the hash suitable for URLs
    base64_encoded = base64.urlsafe_b64encode(md5_hash.encode()).decode()
    return base64_encoded.rstrip("=")

def pack_file(
    file_name: str,
    file_size: int,
    mime_type: str,
    file_id: str
) -> str:
    """
    Packs file information into a JSON string and encodes it.
    """
    # Create a dictionary with file metadata
    data = {
        "file_name": file_name,
        "file_size": file_size,
        "mime_type": mime_type,
        "file_id": file_id
    }
    # Serialize to a compact JSON string and encode
    return json.dumps(data, separators=(",", ":"))

async def get_file_ids(client: TelegramClient, chat_id: int, message_id: int) -> Optional[FileInfo]:
    """
    Retrieves file information from a message in a Telegram channel.
    This function is a wrapper for Telethon's get_messages() and handles
    potential errors with message IDs.
    """
    log = root_log.getChild("file-info")
    
    try:
        msg_id_int = int(message_id)
    except ValueError:
        log.error("Invalid message_id format: %s. Message ID must be a simple integer.", message_id)
        return None

    try:
        message: Message = await client.get_messages(chat_id, ids=[msg_id_int])

        if not message or not message[0]:
            log.warning("Message with ID %s not found in channel %s.", msg_id_int, chat_id)
            return None

        message_obj = message[0]
        
        if not isinstance(message_obj.media, Document):
            log.warning("Message with ID %s does not contain a document.", msg_id_int)
            return None

        document: Document = message_obj.media.document
        
        file_info = FileInfo(
            file_id=str(document.id),
            dc_id=document.dc_id,
            file_size=document.size,
            file_name=document.file_name,
            mime_type=document.mime_type,
            location=document
        )

        return file_info
    
    except MessageIdInvalidError:
        log.error("Message ID %s is invalid or out of range.", msg_id_int)
        return None
    except Exception as e:
        log.error("An unexpected error occurred while fetching message %s: %s", msg_id_int, e)
        return None

