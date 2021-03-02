import asyncio
import enum
import logging
import json
import os
import random
import urllib.parse as up
import sys
import zlib

import aiohttp
import pkg_resources  # part of setuptools
import websockets


__version__ = pkg_resources.require("timer-bot")[0].version
_logger = logging.getLogger()
API_VERSION = 8
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ROOT = f"https://discordapp.com/api/v{API_VERSION}/"
HEADERS = {
    "Authorization": f"Bot {DISCORD_TOKEN}",
    "User-Agent": (
        f"DiscordBot (https://github.com/lionel-panhaleux/timer {__version__}) "
        f"Python/{sys.version_info[0]}.{sys.version_info[1]} "
        f"aiohttp/{aiohttp.__version__}"
    ),
}


@enum.unique
class Intent(enum.IntFlag):
    GUILDS = enum.auto()  # 1 << 0
    GUILD_MEMBERS = enum.auto()  # 1 << 1
    GUILD_BANS = enum.auto()  # 1 << 2
    GUILD_EMOJIS = enum.auto()  # 1 << 3
    GUILD_INTEGRATIONS = enum.auto()  # 1 << 4
    GUILD_WEBHOOKS = enum.auto()  # 1 << 5
    GUILD_INVITES = enum.auto()  # 1 << 6
    GUILD_VOICE_STATES = enum.auto()  # 1 << 7
    GUILD_PRESENCES = enum.auto()  # 1 << 8
    GUILD_MESSAGES = enum.auto()  # 1 << 9
    GUILD_MESSAGE_REACTIONS = enum.auto()  # 1 << 10
    GUILD_MESSAGE_TYPING = enum.auto()  # 1 << 11
    DIRECT_MESSAGES = enum.auto()  # 1 << 12
    DIRECT_MESSAGE_REACTIONS = enum.auto()  # 1 << 13
    DIRECT_MESSAGE_TYPING = enum.auto()  # 1 << 14


@enum.unique
class Opcode(enum.IntEnum):
    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    PRESENCE_UPDATE = 3
    VOICE_STATE_UPDATE = 4
    # opcode 5 is not documented
    RESUME = 6
    RECONNECT = 7
    REQUEST_GUILD_MEMBERS = 8
    INVALID_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11


@enum.unique
class Event(str, enum.ENUM):
    UPDATE_VOICE_STATE = "UPDATE_VOICE_STATE"
    UPDATE_STATUS = "UPDATE_STATUS"
    READY = "READY"
    RESUMED = "RESUMED"
    CHANNEL_CREATE = "CHANNEL_CREATE"
    CHANNEL_UPDATE = "CHANNEL_UPDATE"
    CHANNEL_DELETE = "CHANNEL_DELETE"
    CHANNEL_PINS = "CHANNEL_PINS"
    GUILD_CREATE = "GUILD_CREATE"
    GUILD_UPDATE = "GUILD_UPDATE"
    GUILD_DELETE = "GUILD_DELETE"
    GUILD_BAN_ADD = "GUILD_BAN_ADD"
    GUILD_BAN_REMOVE = "GUILD_BAN_REMOVE"
    GUILD_EMOJIS_UPDATE = "GUILD_EMOJIS_UPDATE"
    GUILD_INTEGRATIONS_UPDATE = "GUILD_INTEGRATIONS_UPDATE"
    GUILD_MEMBER_ADD = "GUILD_MEMBER_ADD"
    GUILD_MEMBER_REMOVE = "GUILD_MEMBER_REMOVE"
    GUILD_MEMBER_UPDATE = "GUILD_MEMBER_UPDATE"
    GUILD_MEMBERS_CHUNK = "GUILD_MEMBERS_CHUNK"
    GUILD_ROLE_CREATE = "GUILD_ROLE_CREATE"
    GUILD_ROLE_UPDATE = "GUILD_ROLE_UPDATE"
    GUILD_ROLE_DELETE = "GUILD_ROLE_DELETE"
    INVITE_CREATE = "INVITE_CREATE"
    INVITE_DELETE = "INVITE_DELETE"
    MESSAGE_CREATE = "MESSAGE_CREATE"
    MESSAGE_UPDATE = "MESSAGE_UPDATE"
    MESSAGE_DELETE = "MESSAGE_DELETE"
    MESSAGE_DELETE = "MESSAGE_DELETE"
    MESSAGE_REACTION_ADD = "MESSAGE_REACTION_ADD"
    MESSAGE_REACTION_REMOVE = "MESSAGE_REACTION_REMOVE"
    MESSAGE_REACTION_REMOVE_ALL = "MESSAGE_REACTION_REMOVE_ALL"
    MESSAGE_REACTION_REMOVE_EMOJI = "MESSAGE_REACTION_REMOVE_EMOJI"
    TYPING_START = "TYPING_START"
    USER_UPDATE = "USER_UPDATE"
    VOICE_SERVER_UPDATE = "VOICE_SERVER_UPDATE"
    WEBHOOKS_UPDATE = "WEBHOOKS_UPDATE"


HEARTBEAT_BYTES = json.dumps({"op": Opcode.HEARTBEAT}).encode("utf-8")
IDENTIFY_BYTES = json.dumps(
    {
        "op": Opcode.IDENTIFY,
        "d": {
            "token": DISCORD_TOKEN,
            "intents": (
                Intent.GUILDS
                + Intent.GUILD_MESSAGES
                + Intent.GUILD_MESSAGE_REACTIONS
                + Intent.DIRECT_MESSAGES
                + Intent.DIRECT_MESSAGE_REACTIONS
            ),
            "properties": {
                "$os": "linux",
                "$browser": "timer-bot",
                "$device": "timer-bot",
            },
        },
    }
).encode("utf-8")


async def api_get(session, url):
    async with session.get(ROOT + url, headers=HEADERS) as response:
        if response.status == 429:  # Rate limiting
            await asyncio.sleep(int(response.headers["Retry-After"]))
            return api_get(session, url)
        response.raise_for_status()
        content = await response.text()
        if response.headers["content-type"] == "application/json":
            return json.loads(content)
        return content


class DiscordClient:
    def __init__(self):
        self.buffer = None
        self.decompress = None
        self.listener = None
        self.websocket = None
        self.heartbeat = None
        self.lock = asyncio.Lock()
        self.session = None
        self.sequence_number = None

    async def reset(self) -> None:
        # stop heartbeat
        if self.heartbeat:
            self.heartbeat.cancel()
        self.heartbeat = None
        # stop receiving messages
        if self.listener:
            self.listener.cancel()
        self.listener = None
        # close websocket
        if self.websocket:
            asyncio.create_task(self.websocket.close())
        self.websocket = None
        # reset buffer and compression context
        self.buffer = bytearray()
        self.zlib_context = zlib.decompressobj()

    async def connect(self, url: str) -> None:
        self.reset()
        gateway_url = (
            url
            + "?"
            + up.urlencode(
                {"v": API_VERSION, "encoding": "json", "compress": "zlib-stream"}
            )
        )
        self.websocket = await websockets.connect(gateway_url)  # do we need ssl=True ?
        self.listener = asyncio.create_task(self.receive())

    async def send(self, op: Opcode, **kwargs) -> None:
        """Use self.websocket.send() to send bytes directly."""
        message = json.dumps({"op": op, "d": kwargs}).encode("utf-8")
        if len(message) > 4096:
            raise ValueError("Message too long (over 4096 bytes)")
        await self.websocket.send(message)

    async def send_heartbeat(self, heartbeat_interval):
        while True:
            await self.websocket.send(HEARTBEAT_BYTES)
            asyncio.sleep(HEARTBEAT_BYTES)

    async def receive(self):
        try:
            async for message in self.websocket:
                asyncio.create_task(self.handle(message))
        except websockets.ConnectionClosedError:
            self.connect()

    async def handle(self, message):
        assert type(message) is bytes
        self.buffer.extend(message)
        if len(message) < 4 or message[-4:] != b"\x00\x00\xff\xff":
            return

        try:
            message = self.zlib_context.decompress(self.buffer)
            self.buffer = bytearray()
            message = json.loads(message.decode("utf-8"))
        except Exception:
            _logger.exception("[WS receive] Failed to decode message")
            raise

        _logger.debug("[WS receive] %s", message)
        if message["op"] == Opcode.DISPATCH:
            self.sequence_number = message["s"]
            await self.dispatch(message["t"], message["d"])
        elif message["op"] == Opcode.RECONNECT:
            await self.reconnect()
        elif message["op"] == Opcode.INVALID_SESSION:
            await self.invalid_session()
        elif message["op"] == Opcode.HELLO:
            await self.hello()
        elif message["op"] == Opcode.HEARTBEAT_ACK:
            self.ack = True
        else:
            raise RuntimeError(f"Unexpected opcode: {message['op']}")

    async def hello(self, data):
        heartbeat_interval = data["heartbeat_interval"] / 1000
        self.heartbeat = asyncio.create_task(self.send_heartbeat(heartbeat_interval))
        async with self.lock:
            if self.session and self.sequence_number:
                await self.send(
                    Opcode.RESUME,
                    token=DISCORD_TOKEN,
                    session_id=self.session["session_id"],
                    seq=self.sequence_number,
                )
                return
        await self.websocket.send(IDENTIFY_BYTES)

    async def invalid_session(self):
        await asyncio.sleep(random.randint(1, 5))
        async with self.lock:
            self.session = None
            self.sequence_number = None
            await self.connect()

    async def dispatch(self, event, payload):
        if event not in Event:
            raise RuntimeError(f"Unexpected event: {event}")
        if event == Event.READY:  # initial event
            async with self.lock:
                self.session = payload


async def main():
    async with aiohttp.ClientSession() as session:
        url = await api_get(session, "/gateway/bot")
    client = DiscordClient()
    await client.connect_websocket(url)
