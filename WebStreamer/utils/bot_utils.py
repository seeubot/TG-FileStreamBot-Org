# This file is a part of TG-FileStreamBot
#
# Modifications made by Deekshith SH, 2024-2025
# Copyright (C) 2024-2025 Deekshith SH

import logging
from WebStreamer.utils.file_properties import FileInfo, pack_file, get_short_hash

log = logging.getLogger(__name__)

def is_check_hash_match(file_info: FileInfo, message_id: int, short_hash: str) -> bool:
    """
    Checks if the given short hash matches the one generated from the file_info.
    This ensures that the URL is valid and has not been tampered with.
    """
    try:
        # Re-generate the full hash and short hash to validate
        full_hash = pack_file(
            file_info.file_name,
            file_info.file_size,
            file_info.mime_type,
            message_id
        )
        generated_short_hash = get_short_hash(full_hash)
        
        return generated_short_hash == short_hash
    except Exception as e:
        log.error(f"Error during hash validation: {e}")
        return False

