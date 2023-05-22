import asyncio
import datetime
import logging
import os
from typing import Optional, Union, TypeVar

import hikari


#: a GatewayBot to post messages because interaction tokens last only 15min
bot = hikari.GatewayBot(token=os.getenv("DISCORD_TOKEN") or "")
#: stores the Discord ID of the "/timer" slash command
COMMAND_ID = []
#: help message for a running timer
RUNNING_TIMER_HELP = (
    f"- </timer display:{COMMAND_ID[0]}> to display it anew\n"
    f"- </timer pause:{COMMAND_ID[0]}> to pause\n"
    f"- </timer resume:{COMMAND_ID[0]}> to resume\n"
    f"- </timer stop:{COMMAND_ID[0]}> to terminate it\n"
    f"- </timer add:{COMMAND_ID[0]}> to add time to it\n"
    f"- </timer sub:{COMMAND_ID[0]}> to substract time from it\n"
)
#: fixed list of times on which to send a notification
THRESHOLDS = [
    0,  # finished
    1 * 60,  # 1min
    5 * 60,  # 5min
    15 * 60,  # 15min
    30 * 60,  # 30min
]
#: timer embed will display seconds starting from this point
DISPLAY_SECONDS = 5 * 60
#: pause will timeout after this point
PAUSE_TIMEOUT = 1800


def main() -> None:
    """Entrypoint"""
    debug = os.getenv("DEBUG")
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)
    bot.run(asyncio_debug=debug)


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
                    min_value=0,
                    max_value=24,
                ),
                hikari.CommandOption(
                    type=hikari.OptionType.INTEGER,
                    name="minutes",
                    min_value=0,
                    max_value=59,
                ),
                hikari.CommandOption(
                    type=hikari.OptionType.BOOLEAN,
                    name="secured",
                ),
            ],
        )
    )
    .add_option(
        hikari.CommandOption(
            type=hikari.OptionType.SUB_COMMAND,
            name="pause",
            description="Pause the timer",
        )
    )
    .add_option(
        hikari.CommandOption(
            type=hikari.OptionType.SUB_COMMAND,
            name="resume",
            description="Resume the timer",
        )
    )
    .add_option(
        hikari.CommandOption(
            type=hikari.OptionType.SUB_COMMAND,
            name="stop",
            description="Stop the timer",
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


@bot.listen()
async def started(event: hikari.StartedEvent) -> None:
    """Sync application commands on startup"""
    logging.info("Timer bot started")
    try:
        # application = await bot.rest.fetch_application()
        registered = await bot.rest.fetch_application_commands(application=event.app)
        if os.getenv("UPDATE") or set(c.name for c in registered) ^ set("timer"):
            logging.info("Updating command")
            registered = await bot.rest.set_application_commands(
                application=event.app,
                commands=COMMAND_TREE,
            )
        COMMAND_ID.clear()
        COMMAND_ID.append(registered[0].id)
    except hikari.ForbiddenError:
        logging.exception("Bot does not have commands permission")
        return
    except hikari.BadRequestError:
        logging.exception("Bot did not manage to update commands")
        return


@bot.listen()
async def stopping(event: hikari.StoppingEvent) -> None:
    """Stop all timers when the bot stops"""
    logging.info("Shutdown: stopping all timers")
    stop_timers = [timer.stop("Server shutdown") for timer in Timer.MAP.values()]
    await asyncio.gather(stop_timers)


@bot.listen()
async def guild_available(event: hikari.GuildAvailableEvent) -> None:
    """Log guild info when the bot connects to a guild"""
    logging.info(
        f"Connected to guild <{event.guild.name}:{event.guild_id}> "
        f"({event.guild.member_count} members, joined {event.guild.joined_at})"
    )


@bot.listen()
async def handle_interaction(event: hikari.InteractionCreateEvent) -> None:
    """Handle interactions"""
    if event.interaction.type == hikari.InteractionType.APPLICATION_COMMAND:
        await handle_command(event.interaction)
    elif event.interaction.type == hikari.InteractionType.MESSAGE_COMPONENT:
        await command_existing_timer(event.interaction, event.interaction.custom_id)


async def handle_command(interaction: hikari.CommandInteraction) -> None:
    """Handle a slash command. Specifically, create the Timer."""
    sub = interaction.options[0]
    if sub.name == "start":
        if Timer.get(interaction.channel_id):
            await interaction.create_initial_response(
                embed=hikari.Embed(
                    title="⏱ Timer already running", description=RUNNING_TIMER_HELP
                ),
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return
        hours = sub.options.get("hours", 0)
        minutes = sub.options.get("minutes", 0)
        total_time = hours * 3600 + minutes * 60
        if not total_time:
            await interaction.create_initial_response(
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
        logging.info(f"[{interaction.channel_id}] Start timer: {hours}h {minutes}min")
        try:
            timer = Timer(
                interaction.channel_id,
                interaction.user.id,
                total_time,
                sub.options.get("secured", False),
            )
            # send message now, just to check it is authorized
            await timer._send_or_update_message()
            asyncio.create_task(timer.run())
        except (hikari.UnauthorizedError, hikari.ForbiddenError):
            await interaction.create_initial_response(
                embed=hikari.Embed(
                    title="⚠️ Missing permission",
                    description="Timer is not allowed to post a message here.",
                ),
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return
        await interaction.create_initial_response(
            "Timer started", flags=hikari.MessageFlag.EPHEMERAL
        )
        return
    interaction.execute()
    # Manipulating an existing timer
    await command_existing_timer(interaction, sub.name, sub.options.get("minutes", 0))


async def command_existing_timer(
    interaction: Union[hikari.CommandInteraction, hikari.ComponentInteraction],
    command: str,
    minutes: int = 0,
):
    """Handle slash commands or component interactions on an existing timer.

    The trick is our components have custom_id matching the subcommand names.
    """
    timer = Timer.get(interaction.channel_id)
    if not timer:
        await interaction.create_initial_response(
            embed=hikari.Embed(
                title="⛔️ No timer running",
                description=(f"Use </timer start:{COMMAND_ID[0]}> to start a timer."),
            ),
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        return
    if timer.secured and interaction.user.id != timer.author_id:
        await interaction.create_initial_response(
            embed=hikari.Embed(
                title="🚫 Unauthorized",
                description=(
                    f"This is a secure timer: only <@{timer.author_id}> "
                    "can manipulate it."
                ),
            ),
            user_mentions=[timer.author_id],
        )
        return
    if command == "stop":
        await timer.stop()
        await interaction.create_initial_response(
            "Timer stopped", flags=hikari.MessageFlag.EPHEMERAL
        )
        return
    if command == "pause":
        await timer.pause()
        await interaction.create_initial_response(
            "Timer paused", flags=hikari.MessageFlag.EPHEMERAL
        )
        return
    if command == "resume":
        await timer.refresh()
        await interaction.create_initial_response(
            "Timer resumed", flags=hikari.MessageFlag.EPHEMERAL
        )
        return
    if command == "display":
        await timer.refresh(resume=False)
        await interaction.create_initial_response(
            "Timer resumed", flags=hikari.MessageFlag.EPHEMERAL
        )
        return
    if command == "add":
        timer.time_left += minutes * 60
        await timer.refresh(resume=False)
        logging.info(f"[{interaction.channel_id}] Added {minutes}min")
        await interaction.create_initial_response(
            f"Time added ({minutes}min)", flags=hikari.MessageFlag.EPHEMERAL
        )
    if command == "sub":
        timer.time_left -= minutes * 60
        await timer.refresh(resume=False)
        logging.info(f"[{interaction.channel_id}] Substracted {minutes}min")
        await interaction.create_initial_response(
            f"Time substracted ({minutes}min)", flags=hikari.MessageFlag.EPHEMERAL
        )


Self = TypeVar("Self", bound="Timer")


class Timer:
    """Timer object: one per channel"""

    MAP = {}  # {channel_id: Timer instance}, singleton shared by all instances

    def __init__(
        self: Self,
        channel_id: hikari.Snowflakeish,
        author_id: hikari.Snowflakeish,
        time: float,
        secured: bool,
    ):
        self.channel_id: hikari.Snowflakeish = channel_id
        self.author_id: hikari.Snowflakeish = author_id
        self.secured: bool = secured
        self.time_reference: float = 0.0
        self.time_left: float = float(time)
        self.thresholds: list[int] = [limit for limit in THRESHOLDS if time > limit]
        # add a threshold on every hour
        for limit in range(1, time // 3600 + 1):
            self.thresholds.append(limit * 3600)
        # internals
        self.message: Optional[hikari.Message] = None
        self.countdown_future: Optional[asyncio.Future] = None
        self.resume_future: Optional[asyncio.Future] = None

    @classmethod
    def get(cls, channel_id: hikari.Snowflakeish) -> Optional[Self]:
        """Retrieve the timer for given channel"""
        return cls.MAP.get(channel_id, None)

    async def countdown(self: Self) -> None:
        """Countdown: update embed, send notifications"""
        while self.time_left > 0.5:
            # update time_left and display
            new_time = asyncio.get_event_loop().time()
            self.time_left -= min(
                self.time_left,
                max(0, new_time - self.time_reference),
            )
            self.time_reference = new_time
            await self._send_or_update_message()
            # pause the timer if a pause has been required (resume_future is set)
            if self.resume_future:
                try:
                    logging.debug(f"[{self.channel_id}] Wait for resume")
                    await self.resume_future
                except asyncio.CancelledError:
                    logging.debug(f"[{self.channel_id}] Pause cancelled - resume")
                except asyncio.TimeoutError:
                    logging.debug(f"[{self.channel_id}] Pause timed out - resume")
                finally:  # in any case resume.
                    logging.debug(f"[{self.channel_id}] Timer resume")
                    self.resume_future = None
                    self.time_reference = asyncio.get_event_loop().time()
            else:
                # update frequency depends on time left
                # if almost finished, wake as soon as the timer is up (no extra second)
                if self.time_left < 2:
                    self.countdown_future = asyncio.ensure_future(
                        asyncio.sleep(self.time_left)
                    )
                # below DISPLAY_SECONDS, a second-by-second display
                elif self.time_left < DISPLAY_SECONDS + 30:
                    # 0.5 would be ideal but Discord API has a 1s rate limitation
                    # so we try to adjust to stay close to round seconds on time_left
                    self.countdown_future = asyncio.ensure_future(asyncio.sleep(1.01))
                # standard minute-by-minute display
                else:
                    self.countdown_future = asyncio.ensure_future(asyncio.sleep(30))
                try:
                    logging.debug(f"[{self.channel_id}] Wait for countdown")
                    await self.countdown_future
                except asyncio.CancelledError:
                    logging.debug(f"[{self.channel_id}] Countdown canceled")
                finally:  # in any case resume.
                    self.countdown_future = None
        # final "Finished" update
        await self._send_or_update_message()

    async def run(self: Self) -> None:
        """Run the timer, update the client.TIMERS map accordingly."""
        logging.debug(f"[{self.channel_id}] Run")
        self.MAP[self.channel] = self
        self.time_reference = asyncio.get_event_loop().time()
        try:
            await self.countdown()
        except asyncio.CancelledError:
            logging.info(f"[{self.channel_id}] Timer cancelled")
            # NOTE: at that point aiohttp may be closed in case of SIGINT/SIGTERM
        except asyncio.TimeoutError:
            logging.exception(f"[{self.channel_id}] Timeout - something went wrong")
            await self.stop()
        except Exception:
            logging.exception(f"[{self.channel_id}] Unhandled exception")
            raise
        finally:
            del self.MAP[self.channel_id]

    async def _delete_message(self: Self) -> None:
        """Delete the timer embed"""
        if not self.message:
            return
        to_delete = self.message
        self.message = None
        try:
            await to_delete.delete()
        except hikari.HikariError:
            pass

    async def stop(self: Self, reason=""):
        """Stop the timer."""
        logging.debug(f"[{self.log_prefix}] Stop")
        if self.time_left >= 0.5:
            await bot.rest.create_message(
                self.channel_id,
                "Stopped with " + self.time_str() + (f" ({reason})" if reason else ""),
            )
        self.time_left = -1
        logging.info(f"[{self.log_prefix}] Timer stopped")
        if self.countdown_future:
            self.countdown_future.cancel()
        if self.resume_future:
            self.resume_future.cancel()
        await self._delete_message()

    async def pause(self: Self):
        """Pause the timer."""
        # don't pause twice
        if self.resume_future:
            return
        logging.debug(f"[{self.log_prefix}] Pause")
        self.resume_future = asyncio.ensure_future(asyncio.sleep(PAUSE_TIMEOUT))
        # cancel countdown
        if self.countdown_future:
            self.countdown_future.cancel()
            self.countdown_future = None

    async def refresh(self: Self, resume=True):
        """Display a new embed."""
        logging.debug(f"[{self.log_prefix}] Refresh")
        await self._delete_message()
        if self.resume_future:
            # this cancels the countdown_future internally
            if resume:
                self.resume_future.cancel()
            else:
                await self._send_or_update_message()
        elif self.countdown_future:
            self.countdown_future.cancel()

    async def _send_or_update_message(self) -> None:
        """Send or update the running timer embed"""
        if self.time_left < 0.5:
            title = "Timer finished"
            description = f"Use </timer start:{COMMAND_ID[0]}> to start a new timer."
            components = hikari.UNDEFINED
        else:
            components = bot.rest.build_message_action_row()
            description = (
                f"Use the buttons or the </timer:{COMMAND_ID[0]}> command "
                "to manipulate the timer."
            )
            if self.resume_future:
                title = "Timer paused: " + _format_time(self.time_left)
                components.add_interactive_button(
                    style=hikari.ButtonStyle.SUCCESS,
                    label="Resume",
                    custom_id="resume",
                    emoji=hikari.UnicodeEmoji("▶️"),
                )

            else:
                title = _format_time(self.time_left)
                components.add_interactive_button(
                    style=hikari.ButtonStyle.PRIMARY,
                    label="Pause",
                    custom_id="pause",
                    emoji=hikari.UnicodeEmoji("⏱"),
                )
            components.add_interactive_button(
                style=hikari.ButtonStyle.DANGER,
                custom_id="stop",
                label="Stop",
                emoji=hikari.UnicodeEmoji("🛑"),
            )
        embed = hikari.Embed(title=title, description=description)
        if self.message:
            # NOTE: timers > 1h will reach a specific Discord rate limit:
            # `30046	Maximum number of edits to messages older than 1 hour`
            # When running their last DISPLAY_SECONDS
            if self.message.timestamp < (
                datetime.datetime.utcnow() - datetime.timedelta(miutes=55)
            ):
                await self._delete_message()
            else:
                try:
                    self.message = await self.message.edit(
                        embed=embed, components=components
                    )
                except hikari.HikariError:
                    await self._delete_message()
        # NOTE: not an else, the previous block can set the message to None
        if not self.message:
            self.message = await bot.rest.create_message(
                channel=self.channel_id, embed=embed, components=components
            )
        if self.thresholds and self.thresholds[-1] >= self.time_left >= 0:
            await bot.rest.create_message(
                channel=self.channel_id,
                content=f"<@{self.author_id}> {_format_time(self.thresholds.pop())}",
                user_mentions=[self.author_id],
            )


def _format_time(time: float) -> str:
    """Returns a human readable string for given time in seconds"""
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
    return f"{max(0, seconds)} seconds remaining"
