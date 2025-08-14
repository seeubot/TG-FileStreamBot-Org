# This file is a part of TG-FileStreamBot
#
# Copyright (C) 2019 Tulir Asokan
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# Modifications made by Deekshith SH, 2024-2025
# Copyright (C) 2024-2025 Deekshith SH

# pylint: disable=protected-access
from collections import OrderedDict
import copy
from typing import AsyncGenerator, Optional, Dict
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
import asyncio
import math

from telethon import TelegramClient
from telethon.crypto import AuthKey
from telethon.network import MTProtoSender
from telethon.tl.functions import InvokeWithLayerRequest
from telethon.tl.functions.auth import ExportAuthorizationRequest, ImportAuthorizationRequest
from telethon.tl.functions.upload import GetFileRequest
from telethon.tl.alltlobjects import LAYER
from telethon.tl.types import DcOption
from telethon.errors import DcIdInvalidError
from telethon.sessions import StringSession

from WebStreamer.utils.util import decrement_counter, increment_counter
from WebStreamer.utils.file_properties import FileInfo, get_file_ids
from WebStreamer.vars import Var

root_log = logging.getLogger(__name__)

if Var.CONNECTION_LIMIT > 25:
    root_log.warning("The connection limit should not be set above 25 to avoid"
                     " infinite disconnect/reconnect loops")

clients_dict = {}
work_loads: Dict[int, int] = {}
StreamBot = TelegramClient(StringSession(Var.SESSION), Var.API_ID, Var.API_HASH, app_version=__version__)
multi_clients = {}

async def initialize_clients():
    """Initializes the multi-client system"""
    global clients_dict
    for i in range(Var.CONNECTION_LIMIT):
        bot_session = StringSession(Var.SESSION+str(i) if i > 0 else Var.SESSION)
        multi_clients[i] = TelegramClient(
            session=bot_session,
            api_id=Var.API_ID,
            api_hash=Var.API_HASH,
            app_version=__version__
        )
        await multi_clients[i].start(bot_token=Var.BOT_TOKEN)
        work_loads[i] = 0
        clients_dict[i] = multi_clients[i]
        logging.info("Client %s initialized successfully", i + 1)
    
    if len(clients_dict) == 0:
        logging.error("Failed to initialize any client.")
        return

@dataclass
class Connection:
    log: logging.Logger
    sender: MTProtoSender
    lock: asyncio.Lock
    users: int = 0


class DCConnectionManager:
    log: logging.Logger
    client: TelegramClient

    dc_id: int
    dc: Optional[DcOption]
    auth_key: Optional[AuthKey]
    connections: list[Connection]

    _list_lock: asyncio.Lock

    def __init__(self, client: TelegramClient, dc_id: int) -> None:
        self.log = root_log.getChild(f"dc{dc_id}")
        self.client = client
        self.dc_id = dc_id
        self.auth_key = None
        self.connections = []
        self._list_lock = asyncio.Lock()
        self.dc = None

    async def _new_connection(self) -> Connection:
        if not self.dc:
            self.dc = await self.client._get_dc(self.dc_id)
        sender = MTProtoSender(self.auth_key, loggers=self.client._log)
        index = len(self.connections) + 1
        conn = Connection(sender=sender, log=self.log.getChild(f"conn{index}"), lock=asyncio.Lock())
        self.connections.append(conn)
        async with conn.lock:
            conn.log.info("Connecting...")
            connection_info = self.client._connection(
                self.dc.ip_address, self.dc.port, self.dc.id,
                loggers=self.client._log,
                proxy=self.client._proxy)
            await sender.connect(connection_info)
            if not self.auth_key:
                await self._export_auth_key(conn)
            return conn

    async def _export_auth_key(self, conn: Connection) -> None:
        self.log.info(f"Exporting auth to DC {self.dc.id}"
                      f" (main client is in {self.client.session.dc_id})")
        try:
            auth = await self.client(ExportAuthorizationRequest(self.dc.id))
        except DcIdInvalidError:
            self.log.debug("Got DcIdInvalidError")
            self.auth_key = self.client.session.auth_key
            conn.sender.auth_key = self.auth_key
            return
        init_request = copy.copy(self.client._init_request)
        init_request.query = ImportAuthorizationRequest(id=auth.id, bytes=auth.bytes)
        req = InvokeWithLayerRequest(LAYER, init_request)
        await conn.sender.send(req)
        self.auth_key = conn.sender.auth_key

    async def _next_connection(self) -> Connection:
        best_conn: Optional[Connection] = None
        if self.connections:
            best_conn = min(self.connections, key=lambda conn: conn.users)
        if (not best_conn or best_conn.users > 0) and len(self.connections) < Var.CONNECTION_LIMIT:
            best_conn = await self._new_connection()
        return best_conn

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[Connection, None]:
        async with self._list_lock:
            conn: Connection = await asyncio.shield(self._next_connection())
            # The connection is locked so reconnections don't stack
            async with conn.lock:
                conn.users += 1
        try:
            yield conn
        finally:
            conn.users -= 1


class ParallelTransferrer:
    log: logging.Logger = logging.getLogger(__name__)
    client: TelegramClient
    lock: asyncio.Lock
    cached_files: OrderedDict[int, asyncio.Task]

    dc_managers: dict[int, DCConnectionManager]

    def __init__(self, client: TelegramClient) -> None:
        self.client = client
        self.dc_managers = {
            1: DCConnectionManager(client, 1),
            2: DCConnectionManager(client, 2),
            3: DCConnectionManager(client, 3),
            4: DCConnectionManager(client, 4),
            5: DCConnectionManager(client, 5),
        }
        self.cached_files = OrderedDict()
        self.lock = asyncio.Lock()

    async def get_file_properties(self, message_id: int) -> Optional[FileInfo]:
        if message_id in self.cached_files:
            return await asyncio.shield(self.cached_files[message_id])
        task=asyncio.create_task(get_file_ids(self.client, Var.BIN_CHANNEL, message_id))
        if Var.CACHE_SIZE is not None and len(self.cached_files) > Var.CACHE_SIZE:
            self.cached_files.popitem(last=False)
        self.cached_files[message_id]=task
        file_id=await asyncio.shield(task)
        if not file_id:
            self.cached_files.pop(message_id)
            logging.debug("File not found for message with ID %s", message_id)
            return None
        logging.debug("Generated file ID for message with ID %s", message_id)
        return file_id

    def post_init(self) -> None:
        self.dc_managers[self.client.session.dc_id].auth_key = self.client.session.auth_key

    async def _int_download(self, request: GetFileRequest, dc_id: int,first_part_cut: int,
        last_part_cut: int, part_count: int, chunk_size: int,
        last_part: int, total_parts: int, index: int, ip: str) -> AsyncGenerator[bytes, None]:
        log = self.log
        try:
            async with self.lock:
                work_loads[index] += 1
                increment_counter(ip)
            current_part = 1
            dcm = self.dc_managers[dc_id]
            async with dcm.get_connection() as conn:
                log = conn.log
                while current_part <= part_count:
                    result = await conn.sender.send(request)
                    request.offset += chunk_size
                    if not result.bytes:
                        break
                    elif part_count == 1:
                        yield result.bytes[first_part_cut:last_part_cut]
                    elif current_part == 1:
                        yield result.bytes[first_part_cut:]
                    elif current_part == part_count:
                        yield result.bytes[:last_part_cut]
                    else:
                        yield result.bytes
                    log.debug("Part %s/%s (total %s) downloaded",current_part,last_part,total_parts)
                    current_part += 1
                log.debug("Parallel download finished")
        except (GeneratorExit, StopAsyncIteration, asyncio.CancelledError):
            log.debug("Parallel download interrupted")
            raise
        except Exception:
            log.debug("Parallel download errored", exc_info=True)
        finally:
            async with self.lock:
                work_loads[index] -= 1
                decrement_counter(ip)
            logging.debug("Finished yielding file with %s parts.",current_part)

    def download(self, file_id: FileInfo, file_size: int, from_bytes: int, until_bytes: int, index: int, ip: str
        ) -> AsyncGenerator[bytes, None]:
        dc_id = file_id.dc_id
        location=file_id.location

        chunk_size = Var.CHUNK_SIZE
        offset = from_bytes - (from_bytes % chunk_size)
        first_part_cut = from_bytes - offset
        first_part = math.floor(offset / chunk_size)
        last_part_cut = until_bytes % chunk_size + 1
        last_part = math.ceil(until_bytes / chunk_size)
        part_count = last_part - first_part
        total_parts = math.ceil(file_size / chunk_size)

        self.log.debug("Starting parallel download: chunks %s-%s"
                       " of %s %s",first_part,last_part,part_count,location)
        request = GetFileRequest(location, offset=offset, limit=chunk_size)

        return self._int_download(request, dc_id, first_part_cut, last_part_cut,
            part_count, chunk_size, last_part, total_parts, index, ip)

