import asyncio
import datetime
import logging
import os
from typing import Optional, Union, Any

import uvloop
import hikari

from . import timer


logger = logging.getLogger("timer")
#: a GatewayBot to post messages because interaction tokens last only 15min
bot = hikari.GatewayBot(token=os.getenv("DISCORD_TOKEN") or "")


def main() -> None:
    """Entrypoint"""
    if __debug__:
        logging.getLogger("hikari").setLevel(logging.DEBUG)
        logging.getLogger("timer").setLevel(logging.DEBUG)
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    bot.run()


#: Components IDs
PAUSE_BUTTON = "pause"
RESUME_BUTTON = "resume"
STOP_BUTTON = "stop"


#: Bot slash commands
COMMAND_TREE = [
    bot.rest.slash_command_builder("timer", "Manage the channel timer")
    .add_option(
        hikari.CommandOption(
            type=hikari.OptionType.SUB_COMMAND,
            name="start",
            description="Start a timer",
            options=[
                hikari.CommandOption(
                    type=hikari.OptionType.INTEGER,
                    name="hours",
                    description="Hours",
                    min_value=0,
                    max_value=24,
                ),
                hikari.CommandOption(
                    type=hikari.OptionType.INTEGER,
                    name="minutes",
                    description="Minutes",
                    min_value=0,
                    max_value=59,
                ),
                hikari.CommandOption(
                    type=hikari.OptionType.BOOLEAN,
                    name="protected",
                    description="Only the timer creator can manage it",
                ),
            ],
        )
    )
    .add_option(
        hikari.CommandOption(
            type=hikari.OptionType.SUB_COMMAND,
            name="add",
            description="Add time to the timer",
            options=[
                hikari.CommandOption(
                    type=hikari.OptionType.INTEGER,
                    name="minutes",
                    description="Minutes",
                    is_required=True,
                    min_value=1,
                    max_value=1440,
                ),
            ],
        )
    )
    .add_option(
        hikari.CommandOption(
            type=hikari.OptionType.SUB_COMMAND,
            name="sub",
            description="Subtract time to the timer",
            options=[
                hikari.CommandOption(
                    type=hikari.OptionType.INTEGER,
                    name="minutes",
                    description="Minutes",
                    is_required=True,
                    min_value=1,
                    max_value=1440,
                ),
            ],
        )
    )
    .add_option(
        hikari.CommandOption(
            type=hikari.OptionType.SUB_COMMAND,
            name="display",
            description="Display the timer anew",
        )
    )
]


#: stores the Discord ID of the "/timer" slash command
class Context:
    def __init__(self):
        self.application_id: Optional[hikari.Snowflakeish] = None
        self.command_id: Optional[hikari.Snowflakeish] = None
        self.timers: dict[hikari.Snowflakeish, TimerManager] = {}


# ; global context
CTX = Context()


# ######################################################################### TimerManager
class TimerManager:
    """Handle the timer display on Discord."""

    #: fixed list of times on which to send a notification
    THRESHOLDS = [
        1 * 60,  # 1min
        5 * 60,  # 5min
        15 * 60,  # 15min
        30 * 60,  # 30min
    ]

    def __init__(
        self,
        initial_time: int,
        channel_id: hikari.Snowflakeish,
        author_id: hikari.Snowflakeish,
        protected: bool = False,
    ):
        self.timer: timer.Timer = timer.Timer(initial_time, self)
        self.channel_id: hikari.Snowflakeish = channel_id
        self.author_id: hikari.Snowflakeish = author_id
        self.protected = protected
        self.message: Optional[hikari.Message] = None
        self.threshold: int = self._next_threshold(initial_time)
        self.lock = asyncio.Lock()

    def _next_threshold(self, time: int) -> Optional[int]:
        """Return the next threshold (strictly) under this time."""
        time = int(time)
        if time > 3600:
            return int((time - 0.1) // 3600) * 3600
        available = [t for t in self.THRESHOLDS if t < time]
        if available:
            return available[-1]
        return None

    async def __call__(self, time_left: float) -> None:
        """Display callback, called every minute or second by the timer."""
        kwargs = self.get_running_kwargs()
        replace_message = True
        async with self.lock:
            if self.message:
                # recreate the message every hour to avoid the Discord 30046 limit:
                # `30046	Maximum number of edits to messages older than 1 hour`
                if self.message.timestamp >= (
                    datetime.datetime.now(datetime.timezone.utc)
                    - datetime.timedelta(minutes=60)
                ):
                    try:
                        self.message = await self.message.edit(**kwargs)
                        replace_message = False
                    except hikari.NotFoundError:
                        self.message = None
                    except hikari.HikariError:
                        pass
            if replace_message:
                res = await asyncio.gather(
                    bot.rest.create_message(channel=self.channel_id, **kwargs),
                    self._delete_message(),
                )
                self.message = res[0]
        # in addition, we want to notify the author on specific THRESHOLDS
        # only use the lowest threshold when timer is modified (eg. 3 hours subtracted)
        threshold = None
        while self.threshold and self.threshold >= time_left:
            threshold = self.threshold
            self.threshold = self._next_threshold(self.threshold)
        if threshold:
            await bot.rest.create_message(
                channel=self.channel_id,
                content=f"<@{self.author_id}> {format_time(threshold)}",
                user_mentions=[self.author_id],
            )
        if time_left <= 0:
            await bot.rest.create_message(
                channel=self.channel_id,
                content=f"<@{self.author_id}> timer finished",
                user_mentions=[self.author_id],
            )

    async def _delete_message(self) -> None:
        """Delete the timer embed."""
        if not self.message:
            return
        try:
            await self.message.delete()
        except (hikari.HikariError, AttributeError):
            logger.exception(f"[{self.channel_id}] Failed to delete message")

    async def shutdown(self) -> None:
        """Shutdown the timer, display an informative message."""
        time_left = self.timer.stop()
        msg = f"**Server shutdown:** Timer stopped ({format_time(time_left)})"
        async with self.lock:
            await asyncio.gather(
                self._delete_message(),
                bot.rest.create_message(channel=self.channel_id, content=msg),
            )

    async def refresh(self) -> None:
        """Display the timer anew"""
        if self.timer.paused:
            kwargs = self.get_paused_kwargs()
        else:
            kwargs = self.get_running_kwargs()
        async with self.lock:
            res = await asyncio.gather(
                bot.rest.create_message(channel=self.channel_id, **kwargs),
                self._delete_message(),
            )
            self.message = res[0]

    def get_running_kwargs(self) -> dict[str, Any]:
        """kwargs for the timer message when the timer is running."""
        if self.timer.left <= 0:
            return {
                "content": hikari.Embed(
                    title="Timer finished",
                    color="#5866F2",
                    description=(
                        f"Use </timer start:{CTX.command_id}> to start a new one."
                    ),
                ).set_thumbnail(hikari.UnicodeEmoji("🏁")),
                "components": [],
            }
        else:
            return {
                "embed": hikari.Embed(
                    title=format_time(self.timer.left),
                    color="#248046",
                    description=(
                        f"Add time with </timer add:{CTX.command_id}>, "
                        f"subtract time with </timer sub:{CTX.command_id}>"
                    ),
                ),
                "components": [
                    bot.rest.build_message_action_row()
                    .add_interactive_button(
                        hikari.ButtonStyle.PRIMARY,
                        PAUSE_BUTTON,
                        label="Pause",
                        emoji=hikari.UnicodeEmoji("⏱"),
                    )
                    .add_interactive_button(
                        hikari.ButtonStyle.DANGER,
                        STOP_BUTTON,
                        label="Stop",
                        emoji=hikari.UnicodeEmoji("🛑"),
                    )
                ],
            }

    def get_paused_kwargs(self) -> dict[str, Any]:
        """kwargs for the timer message when the timer is paused."""
        return {
            "embed": hikari.Embed(
                title="Timer paused: " + format_time(self.timer.left),
                color="#FDC300",
                description=(
                    f"Add time with </timer add:{CTX.command_id}>, "
                    f"subtract time with </timer sub:{CTX.command_id}>"
                ),
            ).set_thumbnail(hikari.UnicodeEmoji("⏱")),
            "components": [
                bot.rest.build_message_action_row()
                .add_interactive_button(
                    hikari.ButtonStyle.SUCCESS,
                    RESUME_BUTTON,
                    label="Resume",
                    emoji=hikari.UnicodeEmoji("▶️"),
                )
                .add_interactive_button(
                    hikari.ButtonStyle.DANGER,
                    STOP_BUTTON,
                    label="Stop",
                    emoji=hikari.UnicodeEmoji("🛑"),
                )
            ],
        }


def format_time(time: float) -> str:
    """Returns a human readable string for remaining time."""
    seconds = round(time % 60)
    if seconds > 59 or time > timer.Timer.DISPLAY_SECONDS:
        seconds = 0
    minutes = round((time - seconds) % 3600 / 60)
    if minutes > 59:
        minutes = 0
    hours = round((time - minutes * 60 - seconds) / 3600)
    if time > 3569:
        return f"{hours}:{minutes:0>2} remaining"
    if time > timer.Timer.DISPLAY_SECONDS:
        return f"{minutes} minutes remaining"
    if minutes:
        return f"{minutes}′ {seconds:0>2}″ remaining"
    return f"{max(0, seconds)} seconds remaining"


# ##################################################################### Bot interactions
@bot.listen()
async def started(event: hikari.StartedEvent) -> None:
    """Sync application commands on startup"""
    logger.info("Timer bot started")
    try:
        application = await bot.rest.fetch_application()
        registered = await bot.rest.fetch_application_commands(application=application)
        if os.getenv("UPDATE") or set(c.name for c in registered) ^ set(["timer"]):
            logger.info(
                "Updating command: "
                f"{set(c.name for c in registered)} does not match {set(['timer'])}"
            )
            registered = await bot.rest.set_application_commands(
                application=application,
                commands=COMMAND_TREE,
            )
        CTX.application_id = application.id
        CTX.command_id = registered[0].id
    except hikari.ForbiddenError:
        logger.exception("Bot does not have commands permission")
        return
    except hikari.BadRequestError:
        logger.exception("Bot did not manage to update commands")
        return


@bot.listen()
async def stopping(event: hikari.StoppingEvent) -> None:
    """Stop all timers when the bot stops"""
    logger.info("Shutdown: stopping all timers")
    channels = list(CTX.timers.keys())
    await asyncio.gather(
        *[CTX.timers[c].shutdown() for c in channels],
        return_exceptions=True,
    )


@bot.listen()
async def guild_available(event: hikari.GuildAvailableEvent) -> None:
    """Log guild info when the bot connects to a guild"""
    logger.info(
        f"Connected to guild <{event.guild.name}:{event.guild_id}> "
        f"({event.guild.member_count} members, joined {event.guild.joined_at})"
    )


@bot.listen()
async def handle_interaction(event: hikari.InteractionCreateEvent) -> None:
    """Handle interactions"""
    if event.interaction.type == hikari.InteractionType.APPLICATION_COMMAND:
        await handle_command(event.interaction)
    elif event.interaction.type == hikari.InteractionType.MESSAGE_COMPONENT:
        await handle_component(event.interaction)


async def handle_command(interaction: hikari.CommandInteraction) -> None:
    """Handle the slash commands (start, add, sub, display)"""
    command = interaction.options[0]
    options = {opt.name: opt.value for opt in (command.options or [])}
    logger.debug(
        "[%s|%s] received command: %s %s",
        interaction.channel_id,
        interaction.guild_id,
        command.name,
        options,
    )
    if command.name == "start":
        if CTX.timers.get(interaction.channel_id):
            logger.info("[%s] timer already running", interaction.channel_id)
            await interaction.create_initial_response(
                hikari.ResponseType.MESSAGE_CREATE,
                embed=hikari.Embed(
                    title="⏱ Timer already running",
                    description=(
                        f"- </timer display:{CTX.command_id}> to display it anew\n"
                        f"- </timer add:{CTX.command_id}> to add time to it\n"
                        f"- </timer sub:{CTX.command_id}> to substract time from it\n\n"
                        "**Use the buttons on the timer to pause, resume or stop it.**"
                    ),
                ),
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return
        hours = options.get("hours", 0)
        minutes = options.get("minutes", 0)
        initial_time = hours * 3600 + minutes * 60
        if initial_time < 60:
            logger.info("[%s] zero time: no timer started", interaction.channel_id)
            await interaction.create_initial_response(
                hikari.ResponseType.MESSAGE_CREATE,
                embed=hikari.Embed(
                    title="Zero time",
                    description=(
                        "You must indicate how many hours/minutes "
                        "you want the timer to run for."
                    ),
                ),
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return
        logger.info(
            "[%s|%s] start timer: %sh %smin",
            interaction.channel_id,
            interaction.guild_id,
            hours,
            minutes,
        )
        manager = TimerManager(
            initial_time,
            interaction.channel_id,
            interaction.user.id,
            protected=options.get("protected", False),
        )
        CTX.timers[interaction.channel_id] = manager
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            "Timer starting",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        # run the timer until completion
        try:
            await asyncio.create_task(manager.timer.run())
        except asyncio.CancelledError:
            pass
        # the timer immediately tries to display: it can miss the permission
        except hikari.ForbiddenError:
            try:
                await interaction.edit_initial_response(
                    "**Missing permission:** The timer bot "
                    "does not have access to this channel"
                )
            # if the timer loses permissions later on, the token might have expired
            except hikari.UnauthorizedError:
                pass
        finally:
            logger.info("[%s] timer finished", interaction.channel_id)
            del CTX.timers[interaction.channel_id]
        return
    manager = await get_timer_manager(interaction)
    if not manager:
        return
    minutes = options.get("minutes", 0)
    if command.name == "add":
        manager.timer.adjust_time(minutes * 60)
        logger.info(f"[{interaction.channel_id}] Added {minutes}min")
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            f"Time added ({minutes}min)",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        if manager.timer.paused:
            await manager.refresh()
        return
    if command.name == "sub":
        if minutes * 60 > manager.timer.left - manager.timer.REFRESH:
            await interaction.create_initial_response(
                hikari.ResponseType.MESSAGE_CREATE,
                "Not enough time: use the stop button to stop the timer",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return
        manager.timer.adjust_time(-minutes * 60)
        logger.info(f"[{interaction.channel_id}] Substracted {minutes}min")
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            f"Time substracted ({minutes}min)",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        if manager.timer.paused:
            await manager.refresh()
        return
    if command.name == "display":
        logger.info("[%s] display timer anew", interaction.channel_id)
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            "Displaying timer anew",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        await manager.refresh()
        return


async def get_timer_manager(
    interaction: Union[hikari.CommandInteraction, hikari.ComponentInteraction]
) -> Optional[TimerManager]:
    """Check for timer existence and protected status, None indicates an error."""
    ret = CTX.timers.get(interaction.channel_id)
    if not ret:
        logger.info("[%s] no timer running", interaction.channel_id)
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            embed=hikari.Embed(
                title="⛔️ No timer running",
                description=(f"Use </timer start:{CTX.command_id}> to start a timer."),
            ),
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        return None
    if ret.protected and ret.author_id != interaction.user.id:
        logger.info("[%s] missing permission to post", interaction.channel_id)
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            embed=hikari.Embed(
                title="🚫 Unauthorized",
                description=(
                    f"Protected timer: only <@{ret.author_id}> can manipulate it."
                ),
            ),
            user_mentions=[ret.author_id],
        )
        return None
    return ret


async def handle_component(interaction: hikari.ComponentInteraction) -> None:
    """Handle the timer buttons (pause, resume, stop)"""
    logger.info(
        "[%s] component interaction: %s",
        interaction.channel_id,
        interaction.custom_id,
    )
    manager = await get_timer_manager(interaction)
    if not manager:
        return
    if interaction.custom_id == PAUSE_BUTTON:
        time_left = manager.timer.pause()
        kwargs = manager.get_paused_kwargs()
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE, **kwargs
        )
    elif interaction.custom_id == RESUME_BUTTON:
        kwargs = manager.get_running_kwargs()
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE, **kwargs
        )
        manager.timer.resume()
    elif interaction.custom_id == STOP_BUTTON:
        manager.running = False
        time_left = manager.timer.stop()
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            hikari.Embed(
                title=f"Timer stopped with {format_time(time_left)}",
                description=f"Use </timer start:{CTX.command_id}> to start a new one.",
            ),
            components=[],
        )
