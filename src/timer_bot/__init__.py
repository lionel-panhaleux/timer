import asyncio
import contextlib
import logging
import os
import typing

import hikari
import hikari.impl

logger = logging.getLogger()
bot = hikari.GatewayBot(
    os.getenv("DISCORD_TOKEN") or "",
    intents=hikari.Intents.NONE,
    logs="DEBUG" if __debug__ else "INFO",
)

DEBUG_GUILD = 161406117686149120
THRESHOLDS = [0, 60, 300, 900, 1800]
DISPLAY_SECONDS = 5 * 60
PAUSE_TIMEOUT = 1800
RUNNING_TIMER_HELP = (
    "- `/timer display` to display it anew\n"
    "- `/timer pause` to pause\n"
    "- `/timer resume` to resume\n"
    "- `/timer stop` to terminate it\n"
    "- `/timer add` to add time to it\n"
    "- `/timer sub` to substract time from it\n"
)

NO_TIMER = "No timer running in this channel. Use `/timer start` to start one."

type Interaction = hikari.CommandInteraction | hikari.ComponentInteraction


class CommandFailed(Exception):
    """A refusal of the user's request, answered ephemerally with its content or embed."""

    def __init__(
        self, content: str = "", embed: hikari.UndefinedOr[hikari.Embed] = hikari.UNDEFINED
    ):
        super().__init__(content)
        self.content = content
        self.embed = embed


def _now() -> float:
    return asyncio.get_running_loop().time()


def time_str(time: float) -> str:
    seconds = round(time % 60)
    if seconds > 59 or time > DISPLAY_SECONDS:
        seconds = 0
    minutes = round((time - seconds) % 3600 / 60)
    if minutes > 59:
        minutes = 0
    hours = round((time - minutes * 60 - seconds) / 3600)
    if time > 3569:
        return f"{hours}:{minutes:0>2} remaining"
    if time > DISPLAY_SECONDS:
        return f"{minutes} minutes remaining"
    if minutes:
        return f"{minutes}′ {seconds:0>2}″ remaining"
    if time > 0:
        return f"{seconds} seconds remaining"
    return "time!"


class Timer:
    """One countdown, in TIMERS under its channel until run() ends.

    Once run() is started, commands only change state and set `wake`, and run() alone writes
    to the channel. A command can still land while a write is awaited: state read before an
    await is stale after it.
    """

    def __init__(
        self, channel_id: hikari.Snowflake, author_id: hikari.Snowflake, time: int, secured: bool
    ):
        self.channel_id = channel_id
        self.author_id = author_id
        self.secured = secured
        self.deadline = _now() + time
        self.paused_left: float | None = None
        self.resume_at = 0.0
        self.thresholds: list[int] = []
        self.message_id: hikari.Snowflake | None = None
        self.repost = False
        self.stopped = False
        self.wake = asyncio.Event()
        self.task: asyncio.Task[None] | None = None
        self._set_thresholds()

    def left(self) -> float:
        if self.paused_left is not None:
            return self.paused_left
        return max(0.0, self.deadline - _now())

    def _set_thresholds(self) -> None:
        left = self.left()
        self.thresholds = [limit for limit in THRESHOLDS if left > limit]
        self.thresholds += [hour * 3600 for hour in range(1, int(left // 3600) + 1)]

    def adjust(self, time: int) -> None:
        if self.paused_left is None:
            self.deadline += time
        else:
            self.paused_left = max(0.0, self.paused_left + time)
        self._set_thresholds()
        self.refresh()

    def pause(self) -> None:
        if self.paused_left is None:
            self.paused_left = self.left()
            self.resume_at = _now() + PAUSE_TIMEOUT
            self.wake.set()

    def resume(self) -> None:
        if self.paused_left is not None:
            self.deadline = _now() + self.paused_left
            self.paused_left = None
            self.wake.set()

    def refresh(self) -> None:
        """Post the embed anew, at the bottom of the channel."""
        self.repost = True
        self.wake.set()

    def stop(self) -> None:
        self.stopped = True
        self.wake.set()

    async def run(self) -> None:
        try:
            while True:
                if self.paused_left is not None:
                    delay = self.resume_at - _now()
                else:
                    left = self.left()
                    delay = 1.1 if left < DISPLAY_SECONDS + 30 else 30
                    if self.thresholds:
                        delay = min(delay, left - self.thresholds[-1])
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.wake.wait(), delay)
                if self.paused_left is not None and _now() >= self.resume_at:
                    self.resume()
                # after resume(), whose wake this pass serves: cleared later, it renders twice
                self.wake.clear()
                if self.stopped:
                    if self.message_id:
                        await self._delete(self.message_id)
                    logger.info("[%s] Timer stopped", self.channel_id)
                    if self.left() > 0:
                        await bot.rest.create_message(
                            self.channel_id, "Stopped with " + time_str(self.left())
                        )
                    return
                await self.render()
                if self.left() <= 0:
                    logger.info("[%s] Timer finished", self.channel_id)
                    return
        except hikari.ClientHTTPResponseError as e:
            logger.info("[%s] Timer dropped, Discord refused: %s", self.channel_id, e)
        except Exception:
            logger.exception("[%s] Timer crashed", self.channel_id)
        finally:
            if TIMERS.get(self.channel_id) is self:
                del TIMERS[self.channel_id]

    async def render(self) -> None:
        left = self.left()
        rows: list[hikari.impl.MessageActionRowBuilder] = []
        if left <= 0:
            title = "Timer finished"
            description = "Use `/timer start` to start a new timer."
        else:
            description = "Use the buttons or the `/timer` commands to manipulate the timer."
            row = hikari.impl.MessageActionRowBuilder()
            if self.paused_left is None:
                title = time_str(left)
                row.add_interactive_button(
                    hikari.ButtonStyle.PRIMARY, "pause", emoji="⏱", label="Pause"
                )
            else:
                title = "Timer paused: " + time_str(left)
                row.add_interactive_button(
                    hikari.ButtonStyle.SUCCESS, "resume", emoji="▶️", label="Resume"
                )
            row.add_interactive_button(hikari.ButtonStyle.DANGER, "stop", emoji="🛑", label="Stop")
            rows = [row]
        embed = hikari.Embed(title=title, description=description)
        if self.repost and self.message_id:
            await self._delete(self.message_id)
            self.message_id = None
        self.repost = False
        if self.message_id:
            try:
                await bot.rest.edit_message(
                    self.channel_id, self.message_id, embed=embed, components=rows
                )
            except hikari.ClientHTTPResponseError as e:
                logger.info("[%s] Failed to edit message: %s", self.channel_id, e)
                old_message_id = self.message_id
                message = await bot.rest.create_message(
                    self.channel_id, embed=embed, components=rows
                )
                self.message_id = message.id
                await self._delete(old_message_id)
        else:
            message = await bot.rest.create_message(self.channel_id, embed=embed, components=rows)
            self.message_id = message.id
        left = self.left()
        if self.thresholds and self.thresholds[-1] >= left:
            # hikari parses no user mention unless told to: the ping would not notify
            await bot.rest.create_message(
                self.channel_id,
                f"<@{self.author_id}> {time_str(self.thresholds.pop())}",
                user_mentions=[self.author_id],
            )

    async def _delete(self, message_id: hikari.Snowflake) -> None:
        try:
            await bot.rest.delete_message(self.channel_id, message_id)
        except hikari.ClientHTTPResponseError as e:
            logger.info("[%s] Failed to delete message: %s", self.channel_id, e)


TIMERS: dict[hikari.Snowflake, Timer] = {}


async def _answer(interaction: Interaction, content: str = "", **kwargs: typing.Any) -> None:
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE, content, flags=hikari.MessageFlag.EPHEMERAL, **kwargs
    )


def _timer(interaction: Interaction) -> Timer:
    timer = TIMERS.get(interaction.channel_id)
    if not timer:
        raise CommandFailed(NO_TIMER)
    return timer


def _owned_timer(interaction: Interaction, verb: str) -> Timer:
    timer = _timer(interaction)
    if timer.secured and interaction.user.id != timer.author_id:
        raise CommandFailed(f"This is a secured timer, only the owner can {verb} it.")
    return timer


async def timer_start(
    interaction: hikari.CommandInteraction, hours: int, minutes: int = 0, secured: bool = False
) -> None:
    channel_id = interaction.channel_id
    if channel_id in TIMERS:
        embed = hikari.Embed(title="Timer already running", description=RUNNING_TIMER_HELP)
        raise CommandFailed(embed=embed)
    total_time = hours * 3600 + minutes * 60
    if not total_time:
        embed = hikari.Embed(title="No time", description="Hours and minutes cannot both be zero.")
        raise CommandFailed(embed=embed)
    # claimed before the first await: a start racing this one finds the channel busy
    timer = TIMERS[channel_id] = Timer(channel_id, interaction.user.id, total_time, secured)
    try:
        await _answer(interaction, "Starting Timer")
        logger.info("[%s] Start timer: %sh %smin", channel_id, hours, minutes)
        try:
            await timer.render()
        except hikari.ClientHTTPResponseError as e:
            logger.info("[%s] Failed to start: %s", channel_id, e)
            await interaction.edit_initial_response(
                "**Failed to start**\nTimer bot requires permission to send messages"
            )
            return
        timer.task = asyncio.create_task(timer.run())
    finally:
        if timer.task is None:
            del TIMERS[channel_id]


async def timer_pause(interaction: Interaction) -> None:
    timer = _owned_timer(interaction, "pause")
    timer.pause()
    if interaction.user.id != timer.author_id:
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            f"<@{timer.author_id}> timer paused by {interaction.user.mention}",
            user_mentions=[timer.author_id, interaction.user.id],
        )
    else:
        await _answer(interaction, "Timer paused")


async def timer_resume(interaction: Interaction) -> None:
    timer = _owned_timer(interaction, "resume")
    timer.resume()
    timer.refresh()
    await _answer(interaction, "Timer resumed")


async def timer_stop(interaction: Interaction) -> None:
    _owned_timer(interaction, "stop").stop()
    await _answer(interaction, "Timer stopped")


async def timer_add(interaction: hikari.CommandInteraction, minutes: int) -> None:
    _owned_timer(interaction, "modify").adjust(minutes * 60)
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE, f"Time added ({minutes}min)"
    )


async def timer_sub(interaction: hikari.CommandInteraction, minutes: int) -> None:
    _owned_timer(interaction, "modify").adjust(-minutes * 60)
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE, f"Time substracted ({minutes}min)"
    )


async def timer_display(interaction: hikari.CommandInteraction) -> None:
    _timer(interaction).refresh()
    await _answer(interaction, "Timer displayed")


def _minutes(min_value: int, max_value: int, required: bool) -> hikari.CommandOption:
    return hikari.CommandOption(
        type=hikari.OptionType.INTEGER,
        name="minutes",
        description="Number of minutes",
        is_required=required,
        min_value=min_value,
        max_value=max_value,
    )


def _subcommand(name: str, description: str, *options: hikari.CommandOption):
    return hikari.CommandOption(
        type=hikari.OptionType.SUB_COMMAND,
        name=name,
        description=description,
        options=list(options),
    )


TIMER_COMMAND = hikari.impl.SlashCommandBuilder(
    "timer",
    "Countdown timer",
    options=[
        _subcommand(
            "start",
            "Start a timer",
            hikari.CommandOption(
                type=hikari.OptionType.INTEGER,
                name="hours",
                description="Number of hours",
                is_required=True,
                min_value=0,
                max_value=24,
            ),
            _minutes(0, 59, required=False),
            hikari.CommandOption(
                type=hikari.OptionType.BOOLEAN,
                name="secured",
                description="Only the owner can modify a secure timer (default false)",
            ),
        ),
        _subcommand("pause", "pause the timer"),
        _subcommand("resume", "resume the timer"),
        _subcommand("stop", "stop the timer"),
        _subcommand("add", "Add time", _minutes(1, 1440, required=True)),
        _subcommand("sub", "Substract time", _minutes(1, 1440, required=True)),
        _subcommand("display", "Display the timer anew"),
    ],
)
COMMANDS: dict[str, typing.Callable[..., typing.Awaitable[None]]] = {
    "start": timer_start,
    "pause": timer_pause,
    "resume": timer_resume,
    "stop": timer_stop,
    "add": timer_add,
    "sub": timer_sub,
    "display": timer_display,
}
#: embeds posted by an earlier process still carry these custom_ids
BUTTONS: dict[str, typing.Callable[[Interaction], typing.Awaitable[None]]] = {
    "pause": timer_pause,
    "resume": timer_resume,
    "stop": timer_stop,
}


@bot.listen()
async def on_started(event: hikari.StartedEvent) -> None:
    application = await bot.rest.fetch_application()
    # a PUT replaces the whole set: commands no longer declared here are deleted
    await bot.rest.set_application_commands(
        application, [TIMER_COMMAND], guild=DEBUG_GUILD if __debug__ else hikari.UNDEFINED
    )
    logger.info("Commands registered")


@bot.listen()
async def on_interaction(event: hikari.InteractionCreateEvent) -> None:
    interaction = event.interaction
    if isinstance(interaction, hikari.CommandInteraction) and interaction.command_name == "timer":
        subcommand = interaction.options[0]
        name, handler = subcommand.name, COMMANDS[subcommand.name]
        kwargs = {option.name: option.value for option in subcommand.options or ()}
    elif isinstance(interaction, hikari.ComponentInteraction) and interaction.custom_id in BUTTONS:
        name, handler = interaction.custom_id, BUTTONS[interaction.custom_id]
        kwargs = {}
    else:
        return
    logger.info("[%s] %s by %s %s", interaction.channel_id, name, interaction.user.username, kwargs)
    try:
        await handler(interaction, **kwargs)
    except CommandFailed as e:
        await _answer(interaction, e.content, embed=e.embed)


def main() -> None:
    bot.run()
