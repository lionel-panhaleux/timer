from typing import Optional, Union
import asyncio
import logging
import os

import interactions


logger = logging.getLogger()
bot = interactions.Client(
    token=os.getenv("DISCORD_TOKEN") or "",
    intents=interactions.Intents.DEFAULT,
)
TIMERS = {}


@bot.event
async def on_ready():
    """Login success"""
    logger.info(f"Logged in as {bot.me.name}")


#: fixed list of times on which to send a notification
THRESHOLDS = [
    0,  # finished
    1 * 60,  # 1min
    5 * 60,  # 5min
    15 * 60,  # 15min
    30 * 60,  # 30min
]

#: timer embed will display seconds starting from this point int time
DISPLAY_SECONDS = 5 * 60

#: pause will timeout after this amount of seconds
PAUSE_TIMEOUT = 1800

#: help message for a running timer
RUNNING_TIMER_HELP = (
    "- `/timer display` to display it anew\n"
    "- `/timer pause` to pause\n"
    "- `/timer resume` to resume\n"
    "- `/timer stop` to terminate it\n"
    "- `/timer add` to add time to it\n"
    "- `/timer sub` to substract time from it\n"
)


class Timer:
    """Timer object: one per channel"""

    def __init__(self, channel, author, time, secured, log_prefix=""):
        self.channel = channel
        self.author = author
        self.secured = secured
        self.start_time = 0
        self.total_time = time
        self.time_left = time
        self.log_prefix = log_prefix + "|internal"
        self.thresholds = []
        for limit in THRESHOLDS:
            if time > limit:
                self.thresholds.append(limit)
        # add a threshold on every hour
        for limit in range(1, time // 3600 + 1):
            self.thresholds.append(limit * 3600)
        # internals
        self.message: Optional[interactions.Message] = None
        self.countdown_future = None  # waiting for time to refresh
        self.resume_future = None  # waiting for resume

    async def countdown(self):
        """Countdown: update embed, send notifications"""
        while self.time_left > 0:
            # update time_left
            if not self.resume_future:
                self.time_left = max(
                    0,
                    self.total_time - max(0, bot._loop.time() - self.start_time),
                )
            await self._send_or_update_message()
            # update frequency depends on time left
            if self.resume_future:
                paused_time = bot._loop.time()
                try:
                    logging.debug(f"[{self.log_prefix}] Wait for resume")
                    await self.resume_future
                except asyncio.CancelledError:
                    logging.debug(f"[{self.log_prefix}] Pause cancelled - resume")
                except asyncio.TimeoutError:
                    logging.debug(f"[{self.log_prefix}] Pause timed out - resume")
                finally:  # in any case resume.
                    logging.debug(f"[{self.log_prefix}] Timer resume")
                    self.resume_future = None
                    self.start_time += bot._loop.time() - paused_time
            else:
                if self.time_left < DISPLAY_SECONDS + 30:
                    # minimum because of Discord rate limitation
                    self.countdown_future = asyncio.ensure_future(asyncio.sleep(1.1))
                else:
                    self.countdown_future = asyncio.ensure_future(asyncio.sleep(30))
                try:
                    logging.debug(f"[{self.log_prefix}] Wait for countdown")
                    await self.countdown_future
                except asyncio.CancelledError:
                    logging.debug(f"[{self.log_prefix}] Countdown canceled")
                finally:  # in any case resume.
                    self.countdown_future = None
        # final "Finished" update
        await self._send_or_update_message()

    async def run(self):
        """Run the timer, update the client.TIMERS map accordingly."""
        logging.debug(f"[{self.log_prefix}] Run")
        TIMERS[self.channel] = self
        self.start_time = bot._loop.time()
        try:
            await self.countdown()
        except asyncio.CancelledError:
            logger.info(f"[{self.log_prefix}] Timer cancelled")
            # at that point aiohttp may be closed in case of SIGINT/SIGTERM
        except asyncio.TimeoutError:
            logger.exception(f"[{self.log_prefix}] Timeout - something went wrong")
            await self.stop()
        except Exception:
            logger.exception(f"[{self.log_prefix}] Unhandled exception")
            raise
        finally:
            del TIMERS[self.channel]

    async def stop(self):
        """Stops the timer."""
        logging.debug(f"[{self.log_prefix}] Stop")
        if self.time_left > 0:
            await self.channel.send("Stopped with " + self.time_str())
        self.time_left = -1
        logger.info(f"[{self.log_prefix}] Timer stopped")
        if self.countdown_future:
            self.countdown_future.cancel()
        if self.resume_future:
            self.resume_future.cancel()
        if self.message:
            await self.message.delete()
            self.message = None

    async def pause(self):
        """Pauses the timer."""
        # don't pause twice
        if self.resume_future:
            return
        logging.debug(f"[{self.log_prefix}] Pause")
        self.resume_future = asyncio.ensure_future(asyncio.sleep(PAUSE_TIMEOUT))
        # cancel countdown
        if self.countdown_future:
            self.countdown_future.cancel()
            self.countdown_future = None

    async def refresh(self, resume=True):
        """Display a new embed."""
        logging.debug(f"[{self.log_prefix}] Refresh")
        if self.message:
            await self.message.delete()
            self.message = None
        if self.resume_future:
            # this cancels the countdown_future internally
            if resume:
                self.resume_future.cancel()
            else:
                await self._send_or_update_message()
        elif self.countdown_future:
            self.countdown_future.cancel()

    async def _send_or_update_message(self):
        """The running timer embed"""
        if self.time_left < 1:
            title = "Timer finished"
            components = []
            description = "Use `/timer start` to start a new timer."
        elif self.resume_future:
            title = "Timer paused: " + self.time_str()
            components = [button_resume, button_stop]
            description = (
                "Use the buttons or the `/timer` commands to manipulate the timer."
            )
        else:
            title = self.time_str()
            components = [button_pause, button_stop]
            description = (
                "Use the buttons or the `/timer` commands to manipulate the timer."
            )
        embeds = [interactions.Embed(title=title, description=description)]
        if self.message:
            try:
                await self.message.edit(embeds=embeds, components=components)
            # messages older than 1h cannot be edited too much, at some point it fails
            except interactions.LibraryException as e:
                logger.info("Failed to edit message: %s", e)
                old_message = self.message
                self.message = await self.channel.send(
                    embeds=embeds, components=components
                )
                try:
                    await old_message.delete()
                except interactions.LibraryException as e:
                    logger.info("Failed to delete old message: %s", e)
                    pass
        else:
            self.message = await self.channel.send(embeds=embeds, components=components)
        if self.thresholds and self.thresholds[-1] >= self.time_left >= 0:
            await self.channel.send(
                f"{self.author.mention} {self._time_str(self.thresholds.pop())}"
            )

    def time_str(self):
        """Time string for the current time left."""
        return self._time_str(self.time_left)

    @staticmethod
    def _time_str(time):
        """Returns a human readable string for given time (int) in seconds"""
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


@bot.event(name="on_message_create")
async def on_message_create(message: interactions.Message):
    """Main message loop"""
    if message.author.id == bot.me.id:
        return

    if message.content.lower().startswith("timer "):
        await message.reply(
            "This bot switched to slash commands. Use `/timer` instead."
        )


@bot.command(name="timer")
async def base_timer_command(ctx: interactions.CommandContext):
    pass


def _get_prefix(ctx: interactions.CommandContext):
    """Prefix used for log messages"""
    if ctx.guild:
        prefix = f"{ctx.guild.name}"
        logger.debug("CTX: %s", ctx)
        logger.debug("extras: %s", ctx._extras)
        logger.debug("channel: %s", ctx.channel)
        logger.debug("channel_id: %s", ctx.channel_id)
        if ctx.channel:
            prefix += f":{ctx.channel.name}"
    else:
        prefix = f"{ctx.author.name}"
    return prefix


@base_timer_command.subcommand(
    name="start",
    description="Start a timer",
    options=[
        interactions.Option(
            name="hours",
            description="Number of hours",
            type=interactions.OptionType.INTEGER,
            required=True,
            min_value=0,
            max_value=24,
        ),
        interactions.Option(
            name="minutes",
            description="Number of minutes",
            type=interactions.OptionType.INTEGER,
            required=False,
            min_value=0,
            max_value=59,
        ),
        interactions.Option(
            name="secured",
            description="Only the owner can modify a secure timer (default false)",
            type=interactions.OptionType.BOOLEAN,
            required=False,
        ),
    ],
)
async def timer_start(
    ctx: interactions.CommandContext,
    hours: int,
    minutes: int = 0,
    secured: bool = False,
):
    """Start a timer"""
    # channel info will miss from threads and voice channels chats
    # see https://github.com/interactions-py/library/issues/1041
    if ctx.channel is interactions.MISSING:
        ctx.channel = interactions.Channel(
            _client=ctx.client, **(await ctx.client.get_channel(ctx.channel_id))
        )
    prefix = _get_prefix(ctx)
    # timer already running in channel
    if ctx.channel_id in TIMERS:
        await ctx.send(
            embeds=[
                interactions.Embed(
                    title="Timer already running", description=RUNNING_TIMER_HELP
                )
            ],
            ephemeral=True,
        )
        return
    # no timer running in channel
    total_time = hours * 3600 + minutes * 60
    if total_time:
        timer = Timer(ctx.channel, ctx.author, total_time, secured, prefix)
        await ctx.send("Starting Timer", ephemeral=True)
        logger.info(f"[{prefix}] Start timer: {hours}h {minutes}min")
        try:
            await timer.run()
        except interactions.LibraryException:
            await ctx.edit(
                "**Failed to start**\nTimer bot requires permission to send messages"
            )
        logger.info(f"[{prefix}] Timer finished")
    else:
        await ctx.send(
            embeds=[
                interactions.Embed(
                    title="No time",
                    description="Hours and minutes cannot both be zero.",
                )
            ],
            ephemeral=True,
        )


@base_timer_command.subcommand(name="pause", description="pause the timer")
async def timer_pause(ctx: interactions.CommandContext):
    """Pause the timer"""
    await _pause_timer(ctx)


@base_timer_command.subcommand(name="resume", description="resume the timer")
async def timer_resume(ctx: interactions.CommandContext):
    """Resume the timer"""
    await _resume_timer(ctx)


@base_timer_command.subcommand(name="stop", description="stop the timer")
async def timer_stop(ctx: interactions.CommandContext):
    """Stop the timer"""
    await _stop_timer(ctx)


@base_timer_command.subcommand(
    name="add",
    description="Add time",
    options=[
        interactions.Option(
            name="minutes",
            description="Number of minutes",
            type=interactions.OptionType.INTEGER,
            required=True,
            min_value=1,
            max_value=1440,
        ),
    ],
)
async def timer_add(ctx: interactions.CommandContext, minutes: int):
    """Add time to the timer"""
    timer = TIMERS.get(ctx.channel, None)
    if not timer:
        await ctx.send(
            "No timer running in this channel. Use `/timer start` to start one.",
            ephemeral=True,
        )
        return
    prefix = _get_prefix(ctx)
    if timer.secured and ctx.author.id != timer.author.id:
        await ctx.send(
            "This is a secured timer, only the owner can modify it.", ephemeral=True
        )
        return
    time = minutes * 60
    timer.total_time += time
    timer.time_left += time
    await timer.refresh(resume=False)
    logger.info(f"[{prefix}] Added {time//60}min and refreshed")
    await ctx.send(f"Time added ({minutes}min)")


@base_timer_command.subcommand(
    name="sub",
    description="Substract time",
    options=[
        interactions.Option(
            name="minutes",
            description="Number of minutes",
            type=interactions.OptionType.INTEGER,
            required=True,
            min_value=1,
            max_value=1440,
        ),
    ],
)
async def timer_sub(ctx: interactions.CommandContext, minutes: int):
    """Substract time from the timer"""
    timer = TIMERS.get(ctx.channel, None)
    if not timer:
        await ctx.send(
            "No timer running in this channel. Use `/timer start` to start one.",
            ephemeral=True,
        )
        return
    prefix = _get_prefix(ctx)
    if timer.secured and ctx.author.id != timer.author.id:
        await ctx.send(
            "This is a secured timer, only the owner can modify it.", ephemeral=True
        )
        return
    time = minutes * 60
    timer.total_time -= time
    timer.time_left -= time
    await timer.refresh(resume=False)
    logger.info(f"[{prefix}] Substracted {time//60}min and refreshed")
    await ctx.send(f"Time substracted ({minutes}min)")


@base_timer_command.subcommand(name="display", description="Display the timer anew")
async def timer_display(ctx: interactions.CommandContext):
    """Discplay the timer anew"""
    timer = TIMERS.get(ctx.channel, None)
    if not timer:
        await ctx.send(
            "No timer running in this channel. Use `/timer start` to start one.",
            ephemeral=True,
        )
        return
    prefix = _get_prefix(ctx)
    await timer.refresh(resume=False)
    await ctx.send("Timer displayed", ephemeral=True)
    logger.info(f"[{prefix}] Refreshed")


button_pause = interactions.Button(
    style=interactions.ButtonStyle.PRIMARY,
    label="Pause",
    custom_id="pause",
    emoji=interactions.Emoji(name="⏱"),
)

button_resume = interactions.Button(
    style=interactions.ButtonStyle.SUCCESS,
    label="Resume",
    custom_id="resume",
    emoji=interactions.Emoji(name="▶️"),
)

button_stop = interactions.Button(
    style=interactions.ButtonStyle.DANGER,
    label="Stop",
    custom_id="stop",
    emoji=interactions.Emoji(name="🛑"),
)


@bot.component("pause")
async def button_pause_response(ctx: interactions.ComponentContext):
    await _pause_timer(ctx)


@bot.component("resume")
async def button_resume_response(ctx: interactions.ComponentContext):
    await _resume_timer(ctx)


@bot.component("stop")
async def button_stop_response(ctx: interactions.ComponentContext):
    await _stop_timer(ctx)


async def _pause_timer(
    ctx: Union[interactions.CommandContext, interactions.ComponentContext]
):
    timer = TIMERS.get(ctx.channel, None)
    if not timer:
        await ctx.send(
            "No timer running in this channel. Use `/timer start` to start one.",
            ephemeral=True,
        )
        return
    prefix = _get_prefix(ctx)
    if timer.secured and ctx.author.id != timer.author.id:
        await ctx.send(
            "This is a secured timer, only the owner can pause it.", ephemeral=True
        )
        return
    await timer.pause()
    logger.info(f"[{prefix}] Paused")
    if ctx.author.id != timer.author.id:
        ephemeral = False
        message = f"{timer.author.mention} timer paused by {ctx.author.mention}"
    else:
        ephemeral = True
        message = f"Timer paused"
    await ctx.send(message, ephemeral=ephemeral)


async def _resume_timer(
    ctx: Union[interactions.CommandContext, interactions.ComponentContext]
):
    timer = TIMERS.get(ctx.channel, None)
    if not timer:
        await ctx.send(
            "No timer running in this channel. Use `/timer start` to start one.",
            ephemeral=True,
        )
        return
    prefix = _get_prefix(ctx)
    if timer.secured and ctx.author.id != timer.author.id:
        await ctx.send(
            "This is a secured timer, only the owner can resume it.", ephemeral=True
        )
        return
    await timer.refresh()
    await ctx.send("Timer resumed", ephemeral=True)
    logger.info(f"[{prefix}] Refreshed and resumed")


async def _stop_timer(
    ctx: Union[interactions.CommandContext, interactions.ComponentContext]
):
    timer = TIMERS.get(ctx.channel, None)
    if not timer:
        await ctx.send(
            "No timer running in this channel. Use `/timer start` to start one.",
            ephemeral=True,
        )
        return
    if timer.secured and ctx.author.id != timer.author.id:
        await ctx.send(
            "This is a secured timer, only the owner can stop it.", ephemeral=True
        )
        return
    await timer.stop()
    await ctx.send("Timer stopped", ephemeral=True)


def main():
    """Entrypoint"""
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.DEBUG if __debug__ else logging.INFO)
    bot.start()
    logger.setLevel(logging.NOTSET)
