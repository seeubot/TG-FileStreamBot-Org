# This file is a part of TG-FileStreamBot
#
# Modifications made by Deekshith SH, 2024-2025
# Copyright (C) 2024-2025 Deekshith SH

# pylint: disable=protected-access

import logging
from dataclasses import dataclass
from typing import Optional, List
from telethon import TelegramClient
from telethon.tl.types import Message, Document, Channel
from telethon.errors import MessageIdInvalidError

root_log = logging.getLogger(__name__)

@dataclass
class FileInfo:
    file_id: str
    dc_id: int
    location: Document
    # You can add more attributes here as needed

async def get_file_ids(client: TelegramClient, chat_id: int, message_id: int) -> Optional[FileInfo]:
    """
    Retrieves file information from a message in a Telegram channel.
    This function is a wrapper for Telethon's get_messages() and handles
    potential errors with message IDs.
    """
    log = root_log.getChild("file-info")
    
    try:
        # The message_id must be a simple integer.
        # This will raise a ValueError if it is not.
        msg_id_int = int(message_id)

    except ValueError:
        log.error("Invalid message_id format: %s. Message ID must be a simple integer.", message_id)
        return None

    try:
        # get_messages expects a list of integer IDs.
        message: Message = await client.get_messages(chat_id, ids=[msg_id_int])

        # If no message is found, message[0] will be None
        if not message or not message[0]:
            log.warning("Message with ID %s not found in channel %s.", msg_id_int, chat_id)
            return None

        message_obj = message[0]
        
        if not isinstance(message_obj.media, Document):
            log.warning("Message with ID %s does not contain a document.", msg_id_int)
            return None

        document: Document = message_obj.media.document
        
        # We now have a valid document object, extract its properties.
        # This is where the long integer from the traceback originates from a different file.
        file_info = FileInfo(
            file_id=str(document.id), # Store as a string
            dc_id=document.dc_id,
            location=document
        )

        return file_info
    
    except MessageIdInvalidError:
        log.error("Message ID %s is invalid or out of range.", msg_id_int)
        return None
    except Exception as e:
        log.error("An unexpected error occurred while fetching message %s: %s", msg_id_int, e)
        return None

