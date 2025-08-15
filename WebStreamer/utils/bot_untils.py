# This file is a part of TG-FileStreamBot
#
# Modifications made by Deekshith SH, 2024-2025
# Copyright (C) 2024-2025 Deekshith SH

from WebStreamer.utils.file_properties import pack_file, get_short_hash, FileInfo

def is_check_hash_match(file_info: FileInfo, hash_value: str) -> bool:
    """
    Checks if the given hash value matches the file's hash.
    This prevents unauthorized access to files.
    """
    if not hash_value:
        return False
        
    full_hash = pack_file(
        file_info.file_name,
        file_info.file_size,
        file_info.mime_type,
        file_info.file_id
    )
    
    return get_short_hash(full_hash) == hash_value


