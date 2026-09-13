"""Discord and the clock, the two things with no local real thing.

Discord is hikari's REST client, swapped for a stand-in that records what the bot sends
and refuses on request. Interactions are Discord's own payloads, deserialized by hikari:
the handlers receive the real objects. Time is an event loop whose clock jumps to the
next scheduled callback instead of waiting for it.
"""

import asyncio
import base64
import dataclasses
import inspect
import itertools
import logging
import os
import selectors
import typing

import pytest

# hikari parses the token in GatewayBot.__init__, which runs at import. Assembled rather
# than written out: a literal of this shape is what a secret scanner is built to catch.
os.environ["DISCORD_TOKEN"] = ".".join(
    (
        base64.b64encode(b"123456789012345678").decode(),
        "GaBcDe",
        "FgHiJkLmNoPqRsTuVwXyZ1234567890abcdefg",
    )
)

import hikari

import timer_bot

APPLICATION = 715294649836765285
GUILD = 161406117686149120
CHANNEL = 800000000000000001
AUTHOR = 900000000000000001
OTHER = 900000000000000002

_ids = itertools.count(100000000000000000)


class Clock(selectors.DefaultSelector):
    """A selector that never blocks: waiting for the next callback advances the clock."""

    now = 1000.0

    def select(self, timeout: float | None = None) -> list[tuple[selectors.SelectorKey, int]]:
        if timeout is None:
            raise AssertionError("the loop waits on nothing: the test would hang")
        self.now += timeout
        return super().select(0)


class VirtualLoop(asyncio.SelectorEventLoop):
    def __init__(self) -> None:
        self.clock = Clock()
        super().__init__(self.clock)

    def time(self) -> float:
        return self.clock.now


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    if not inspect.iscoroutinefunction(pyfuncitem.obj):
        return None
    arguments = inspect.signature(pyfuncitem.obj).parameters
    kwargs = {name: pyfuncitem.funcargs[name] for name in arguments}
    with asyncio.Runner(loop_factory=VirtualLoop) as runner:
        runner.run(pyfuncitem.obj(**kwargs))
    return True


def now() -> float:
    return asyncio.get_running_loop().time()


@dataclasses.dataclass
class Message:
    id: hikari.Snowflake
    channel: int
    content: str | None
    title: str | None
    buttons: list[str]
    mentions: list[int]
    at: float
    deleted: bool = False
    #: (time, title) of every update, the post included
    updates: list[tuple[float, str | None]] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Response:
    token: str
    user: int
    content: str | None
    title: str | None
    description: str | None
    ephemeral: bool
    mentions: list[int]


def _given(value: typing.Any) -> typing.Any:
    return None if value is hikari.UNDEFINED else value


def _buttons(components: typing.Any) -> list[str]:
    return [button.custom_id for row in _given(components) or () for button in row.components]


def _mentions(user_mentions: typing.Any) -> list[int]:
    return [int(user) for user in _given(user_mentions) or ()]


class Discord:
    """Stands in for `bot.rest`, whose methods it mirrors by name and parameters."""

    def __init__(self) -> None:
        self.messages: list[Message] = []
        self.responses: list[Response] = []
        #: method name -> for each of its next calls, whether it is refused with a 403
        self.refuse: dict[str, list[bool]] = {}
        #: seconds every call takes to come back, during which the bot's other tasks run
        self.latency = 0.0
        self.commands: typing.Any = None
        self.guild: typing.Any = None
        self._users: dict[str, int] = {}

    async def _call(self, method: str) -> None:
        if self.latency:
            await asyncio.sleep(self.latency)
        if self.refuse.get(method) and self.refuse[method].pop(0):
            raise hikari.ForbiddenError(url=method, headers={}, raw_body="", code=50013)

    def _message(self, message: typing.Any) -> Message:
        found = next(m for m in self.messages if m.id == int(message))
        if found.deleted:
            raise hikari.NotFoundError(url="message", headers={}, raw_body="", code=10008)
        return found

    def channel(self, channel: int = CHANNEL) -> list[Message]:
        return [m for m in self.messages if m.channel == channel and not m.deleted]

    def embeds(self, channel: int = CHANNEL) -> list[Message]:
        return [m for m in self.channel(channel) if m.title]

    def embed(self, channel: int = CHANNEL) -> Message:
        (embed,) = self.embeds(channel)
        return embed

    def texts(self, channel: int = CHANNEL) -> list[Message]:
        return [m for m in self.channel(channel) if m.content]

    async def fetch_application(self) -> typing.Any:
        return hikari.Snowflake(APPLICATION)

    async def set_application_commands(
        self, application: typing.Any, commands: typing.Any, guild: typing.Any = hikari.UNDEFINED
    ) -> typing.Any:
        self.commands, self.guild = commands, guild
        return []

    async def create_message(
        self,
        channel: typing.Any,
        content: typing.Any = hikari.UNDEFINED,
        *,
        embed: typing.Any = hikari.UNDEFINED,
        components: typing.Any = hikari.UNDEFINED,
        user_mentions: typing.Any = hikari.UNDEFINED,
    ) -> Message:
        await self._call("create_message")
        title = _given(embed) and embed.title
        message = Message(
            id=hikari.Snowflake(next(_ids)),
            channel=int(channel),
            content=_given(content),
            title=title,
            buttons=_buttons(components),
            mentions=_mentions(user_mentions),
            at=now(),
            updates=[(now(), title)],
        )
        self.messages.append(message)
        return message

    async def edit_message(
        self,
        channel: typing.Any,
        message: typing.Any,
        content: typing.Any = hikari.UNDEFINED,
        *,
        embed: typing.Any = hikari.UNDEFINED,
        components: typing.Any = hikari.UNDEFINED,
    ) -> Message:
        await self._call("edit_message")
        found = self._message(message)
        found.title = embed.title
        found.buttons = _buttons(components)
        found.updates.append((now(), found.title))
        return found

    async def delete_message(self, channel: typing.Any, message: typing.Any) -> None:
        await self._call("delete_message")
        self._message(message).deleted = True

    async def create_interaction_response(
        self,
        interaction: typing.Any,
        token: str,
        response_type: typing.Any,
        content: typing.Any = hikari.UNDEFINED,
        *,
        flags: typing.Any = hikari.UNDEFINED,
        tts: typing.Any = hikari.UNDEFINED,
        attachment: typing.Any = hikari.UNDEFINED,
        attachments: typing.Any = hikari.UNDEFINED,
        component: typing.Any = hikari.UNDEFINED,
        components: typing.Any = hikari.UNDEFINED,
        embed: typing.Any = hikari.UNDEFINED,
        embeds: typing.Any = hikari.UNDEFINED,
        poll: typing.Any = hikari.UNDEFINED,
        mentions_everyone: typing.Any = hikari.UNDEFINED,
        user_mentions: typing.Any = hikari.UNDEFINED,
        role_mentions: typing.Any = hikari.UNDEFINED,
    ) -> None:
        await self._call("create_interaction_response")
        self.responses.append(
            Response(
                token=token,
                user=self._users[token],
                content=_given(content),
                title=_given(embed) and embed.title,
                description=_given(embed) and embed.description,
                ephemeral=bool(_given(flags) and flags & hikari.MessageFlag.EPHEMERAL),
                mentions=_mentions(user_mentions),
            )
        )

    async def edit_interaction_response(
        self,
        application: typing.Any,
        token: str,
        content: typing.Any = hikari.UNDEFINED,
        *,
        attachment: typing.Any = hikari.UNDEFINED,
        attachments: typing.Any = hikari.UNDEFINED,
        component: typing.Any = hikari.UNDEFINED,
        components: typing.Any = hikari.UNDEFINED,
        embed: typing.Any = hikari.UNDEFINED,
        embeds: typing.Any = hikari.UNDEFINED,
        mentions_everyone: typing.Any = hikari.UNDEFINED,
        user_mentions: typing.Any = hikari.UNDEFINED,
        role_mentions: typing.Any = hikari.UNDEFINED,
    ) -> None:
        await self._call("edit_interaction_response")
        response = next(r for r in self.responses if r.token == token)
        response.content = _given(content)

    def response(self) -> Response:
        """The last answer to an interaction."""
        return self.responses[-1]

    # ################################################################## interactions
    def _base(self, user: int, channel: int, channel_type: int) -> dict[str, typing.Any]:
        token = f"token-{next(_ids)}"
        self._users[token] = user
        channel_payload: dict[str, typing.Any] = {
            "id": str(channel),
            "type": channel_type,
            "name": "a channel",
            "permissions": "0",
        }
        if channel_type == hikari.ChannelType.GUILD_PUBLIC_THREAD:
            channel_payload["parent_id"] = str(CHANNEL)
            channel_payload["thread_metadata"] = {
                "archived": False,
                "auto_archive_duration": 1440,
                "archive_timestamp": "2026-09-13T00:00:00+00:00",
                "locked": False,
            }
        return {
            "id": str(next(_ids)),
            "application_id": str(APPLICATION),
            "token": token,
            "version": 1,
            "guild_id": str(GUILD),
            "channel_id": str(channel),
            "channel": channel_payload,
            "member": {
                "user": {
                    "id": str(user),
                    "username": f"user{user % 10}",
                    "discriminator": "0",
                    "avatar": None,
                },
                "roles": [],
                "joined_at": "2020-01-01T00:00:00+00:00",
                "deaf": False,
                "mute": False,
                "permissions": "0",
            },
            "locale": "en-US",
            "guild_locale": "en-US",
            "app_permissions": "0",
            "entitlements": [],
            "authorizing_integration_owners": {},
            "context": 0,
            "attachment_size_limit": 10485760,
        }

    async def command(
        self,
        subcommand: str,
        user: int = AUTHOR,
        channel: int = CHANNEL,
        channel_type: int = hikari.ChannelType.GUILD_TEXT,
        **options: int | bool,
    ) -> None:
        """Run `/timer <subcommand>` as Discord would deliver it."""
        payload = self._base(user, channel, channel_type)
        payload["type"] = hikari.InteractionType.APPLICATION_COMMAND
        payload["data"] = {
            "id": str(next(_ids)),
            "name": "timer",
            "type": 1,
            "options": [
                {
                    "name": subcommand,
                    "type": hikari.OptionType.SUB_COMMAND,
                    "options": [
                        {
                            "name": name,
                            "type": hikari.OptionType.BOOLEAN
                            if isinstance(value, bool)
                            else hikari.OptionType.INTEGER,
                            "value": value,
                        }
                        for name, value in options.items()
                    ],
                }
            ],
        }
        await self._dispatch(payload)

    async def click(self, custom_id: str, user: int = AUTHOR, channel: int = CHANNEL) -> None:
        """Click a button on the channel's timer embed, or on one long gone."""
        embeds = [m for m in self.messages if m.channel == channel and m.title]
        message_id = embeds[-1].id if embeds else next(_ids)
        payload = self._base(user, channel, hikari.ChannelType.GUILD_TEXT)
        payload["type"] = hikari.InteractionType.MESSAGE_COMPONENT
        payload["data"] = {"custom_id": custom_id, "component_type": 2}
        payload["message"] = {
            "id": str(message_id),
            "channel_id": str(channel),
            "author": {
                "id": str(APPLICATION),
                "username": "Timer",
                "discriminator": "0",
                "avatar": None,
            },
            "content": "",
            "timestamp": "2026-09-13T00:00:00+00:00",
            "edited_timestamp": None,
            "tts": False,
            "mention_everyone": False,
            "mentions": [],
            "mention_roles": [],
            "attachments": [],
            "embeds": [],
            "pinned": False,
            "type": 0,
            "flags": 0,
        }
        await self._dispatch(payload)

    async def _dispatch(self, payload: dict[str, typing.Any]) -> None:
        interaction = timer_bot.bot.entity_factory.deserialize_interaction(payload)
        event = hikari.InteractionCreateEvent(
            shard=typing.cast(typing.Any, None), interaction=interaction
        )
        await timer_bot.bot.dispatch(event, return_tasks=True)
        # let the timer's own task take what the interaction woke it for
        await asyncio.sleep(0.01)


@pytest.fixture
def discord(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> typing.Iterator[Discord]:
    fake = Discord()
    monkeypatch.setattr(timer_bot.bot, "_rest", fake)
    timer_bot.TIMERS.clear()
    yield fake
    # hikari logs a listener's exception instead of raising it, as a timer's task does
    errors = [r for r in caplog.get_records("call") if r.levelno >= logging.ERROR]
    assert not [r.getMessage() for r in errors]
