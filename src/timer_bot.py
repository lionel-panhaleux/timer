import asyncio
import logging
import os
import re

import discord

logger = logging.getLogger()
client = discord.Client()
client.TIMERS = {}


@client.event
async def on_ready():
    """Login success informative log."""
    logger.info(f"Logged in as {client.user}")


#: regex use to parse time expression for timer initialisation
REGEX = (
    r"^\s*(?P<high>\d{1,2})"
    r"\s*((?P<fraction>\.\d+)|(?P<separator>:|')(?P<low>\d{1,2})?)?"
    r"\s*(?P<unit>h|hour|mn|min|minute|s|second)?s?\s*'*\s*$"
)

#: multipliers for accepted time units
MULTIPLIER = {
    "h": 3600,
    "hour": 3600,
    "mn": 60,
    "min": 60,
    "minute": 60,
    "s": 1,
    "second": 1,
}

#: fixed list of times on which to send a notification
THRESHOLDS = [
    1 * 60,  # 1min
    5 * 60,  # 5min
    15 * 60,  # 15min
    30 * 60,  # 30min
    1 * 3600,  # 1h
    2 * 3600,  # 2h
    3 * 3600,  # ...
    4 * 3600,
    5 * 3600,
    6 * 3600,
    7 * 3600,
    8 * 3600,
    9 * 3600,
    10 * 3600,
    11 * 3600,
    12 * 3600,
    24 * 3600,
    36 * 3600,
    48 * 3600,
]

#: timer embed will display seconds starting from this point int time
DISPLAY_SECONDS = 5 * 60

#: pause will timeout after this amount of seconds
PAUSE_TIMEOUT = 1800

#: help message for a running timer
RUNNING_TIMER_HELP = (
    "- `timer` to display it anew\n"
    "- `timer stop` to terminate it\n"
    "- `timer pause` to pause\n"
    "- `timer resume` to resume\n"
    "- `timer add 5` to add 5mn to it\n"
    "- `timer sub 1h` to substract 1h from it\n"
)


class Timer:
    """Timer object: one per channel"""

    def __init__(self, channel, author, start_time, time, log_prefix=""):
        self.channel = channel
        self.author = author
        self.start_time = start_time
        self.total_time = time
        self.time_left = time
        self.log_prefix = log_prefix + "|internal"
        self.thresholds = []
        for limit in THRESHOLDS:
            if time > limit:
                self.thresholds.append(limit)
        # internals
        self.message = None
        self.reaction_future = None  # waiting for user reaction on embed
        self.unpause_future = None  # waiting for remove reaction to unpause

    async def countdown(self):
        """Countdown: update embed, send notifications
        """
        while self.time_left > 0:
            # update frequency depends on time left
            if self.time_left < DISPLAY_SECONDS:
                # minimum because of Discord rate limitation
                await asyncio.sleep(1)
            else:
                await asyncio.sleep(30)
            if self.unpause_future:
                continue
            await self.update_time_left()
            # update the embed, send a notification if we have hit a threshold
            if self.message:
                await self.message.edit(embed=self.embed())
            if self.thresholds and self.thresholds[-1] >= self.time_left:
                await self.channel.send(
                    f"{self.author.mention} {self._time_str(self.thresholds.pop())}"
                )
        await self.stop()

    async def update_time_left(self):
        """Used by refresh and countdown."""
        self.time_left = max(
            0, self.total_time - max(0, client.loop.time() - self.start_time),
        )

    async def wait_reaction(self):
        """Displays the message, wait for a "pause" or "stop" reactions."""
        while self.time_left > 0:
            if not self.message:
                self.message = await self.channel.send(embed=self.embed())
                logging.info(f"[{self.log_prefix}] New embed")
                try:
                    for reaction in ["⏱", "🛑"]:
                        await self.message.add_reaction(reaction)
                except discord.Forbidden:
                    logging.warning(f"[{self.log_prefix}] Missing reaction permission")
            self.reaction_future = asyncio.ensure_future(
                client.wait_for(
                    "reaction_add",
                    # avoid timeouting before countdown finishes, even if paused
                    timeout=self.time_left + PAUSE_TIMEOUT + 60,
                    check=lambda reaction, user: (
                        reaction.message.id == self.message.id
                        and str(reaction.emoji) in ["⏱", "🛑"]
                        and user != client.user
                    ),
                )
            )
            try:
                reaction, user = await self.reaction_future
            except asyncio.CancelledError:  # refresh, stop
                logging.info(f"[{self.log_prefix}] Reaction cancelled")
                continue  # if refreshed, there is time left. If stopped, loop will end
            except asyncio.TimeoutError:  # timeout, should not happen, just continue
                logging.info(f"[{self.log_prefix}] Timed out")
                continue
            self.reaction_future = None
            if reaction.emoji == "🛑":
                logger.info(f"[{self.log_prefix}] ({user.name}) reaction stop")
                await self.stop()
                return
            if reaction.emoji == "⏱":
                logger.info(f"[{self.log_prefix}] ({user.name}) reaction pause")
                await self.pause(user)

    async def run(self):
        """Run the timer, update the client.TIMERS map accordingly."""
        client.TIMERS[self.channel] = self
        self.run_future = asyncio.gather(self.countdown(), self.wait_reaction())
        try:
            await self.run_future
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            logger.exception(f"[{self.log_prefix}] Timeout - something went wrong")
            self.stop()
        finally:
            del client.TIMERS[self.channel]

    async def stop(self):
        """Stops the timer. Used internally but can be called externally."""
        if self.time_left > 0:
            await self.channel.send("Stopped with " + self.time_str())
        else:
            await self.channel.send(f"{self.author.mention} Finished")
        self.time_left = 0
        logger.info(f"[{self.log_prefix}] Timer stopped")
        self.run_future.cancel()
        if self.message:
            await self.message.delete()
            self.message = None

    async def pause(self, user):
        """Pauses the timer. Used internally but can be called externally."""
        if self.unpause_future:
            return
        paused_time = client.loop.time()
        paused_message = self.message
        self.unpause_future = asyncio.ensure_future(
            client.wait_for(
                "reaction_remove",
                timeout=PAUSE_TIMEOUT,
                # beware not to trigger on our own reaction, they are added async
                check=lambda reaction, ruser: (
                    reaction.message.id == self.message.id
                    and str(reaction.emoji) == "⏱"
                    and ruser == user
                ),
            )
        )
        if paused_message:
            await self.message.edit(embed=self.embed())
            await self.message.remove_reaction("🛑", client.user)
        if user != self.author:
            await self.channel.send(f"{self.author.mention} paused by {user.mention}")
        try:
            await self.unpause_future
        except asyncio.CancelledError:
            logging.info(f"[{self.log_prefix}] Pause cancelled - resume")
        except asyncio.TimeoutError:
            logging.info(f"[{self.log_prefix}] Pause timed out - resume")
        finally:  # in any case resume.
            self.unpause_future = None
            self.start_time += client.loop.time() - paused_time
        try:
            await paused_message.edit(embed=self.embed())
            await paused_message.add_reaction("🛑")
        # in case of a refresh, self.message may have changed already
        except discord.errors.NotFound:
            pass

    async def refresh(self):
        """Display a new embed."""
        if self.unpause_future:
            self.unpause_future.cancel()
        if self.message:
            await self.message.delete()
            self.message = None
        await self.update_time_left()
        if self.reaction_future:
            self.reaction_future.cancel()

    def embed(self):
        """The running timer embed"""
        if self.time_left < 1:
            return discord.Embed(title="Finished")
        if self.unpause_future:
            title = "Timer paused: " if self.unpause_future else ""
            description = "Click the ⏱reaction again to unpause."
        else:
            title = ""
            description = "Click the ⏱reaction to pause, 🛑 to terminate."
        title += self.time_str()
        return discord.Embed.from_dict({"title": title, "description": description})

    def time_str(self):
        """Time string for the current time left."""
        return self._time_str(self.time_left)

    @staticmethod
    def _time_str(time):
        """Returns a human readable string for given time (int) in seconds"""
        if time > 3600:
            return f"{int(time / 3600):0>2}:{round(time % 3600 / 60):0>2} remaining"
        if time > DISPLAY_SECONDS:
            return f"{int(time / 60)} minutes remaining"
        if time >= 60:
            return f"{int(time / 60)}′ {round(time % 60):0>2}″ remaining"
        return f"{round(time)} seconds remaining"


@client.event
async def on_message(message):
    """Main message loop"""
    if message.author == client.user:
        return
    if not message.content.lower().startswith("timer"):
        return

    content = message.content[5:].strip()
    if message.guild:
        prefix = f"{message.guild.name}"
        prefix += f":{message.channel.name}"
    else:
        prefix = f"{message.author.name}"
    logger.info(f"[{prefix}] Received: {content}")
    # timer already running in channel
    if message.channel in client.TIMERS:
        timer = client.TIMERS[message.channel]
        if content:
            if content.lower() == "stop":
                await timer.stop()
            elif content.lower() == "resume":
                await timer.refresh()
                logger.info(f"[{prefix}] Refreshed and resumed")
            elif content.lower() == "pause":
                await timer.pause(message.author)
                logger.info(f"[{prefix}] Paused")
            elif content.lower()[:4] == "add ":
                content = content[4:]
                time = get_initial_time(content, default="minute")
                timer.total_time += time
                await timer.refresh()
                logger.info(f"[{prefix}] Added {time} and refreshed")
            elif content.lower()[:4] == "sub ":
                content = content[4:]
                time = get_initial_time(content, default="minute")
                timer.total_time -= time
                await timer.refresh()
                logger.info(f"[{prefix}] Substracted {time} and refreshed")
            else:
                await message.channel.send(
                    embed=discord.Embed(
                        title="Timer already running", description=RUNNING_TIMER_HELP,
                    )
                )
        else:
            if timer.unpause_future:
                await message.channel.send(
                    embed=discord.Embed(
                        title="Timer paused with " + timer.time_str(),
                        description=(
                            "- `timer resume` to resume and display it anew\n"
                            "- `timer stop` to terminate it\n"
                        ),
                    )
                )
            else:
                await timer.refresh()
                logger.info(f"[{prefix}] Refreshed")
        return
    # no timer running in channel
    total_time = get_initial_time(content)
    if total_time:
        timer = Timer(
            message.channel, message.author, client.loop.time(), total_time, prefix
        )
        await timer.run()
        logger.info(f"[{prefix}] Initial timer finished")
    # if parsing fails, display help
    # ignore message with more the 2 words
    else:
        if len(content.split()) > 2:
            return
        await message.channel.send(
            embed=discord.Embed.from_dict(
                {
                    "title": "Usage",
                    "fields": [
                        {
                            "name": "Start a timer",
                            "value": (
                                "- `timer 2h` starts a 2 hours timer\n"
                                "- `timer 2.5` starts a 2 hours 30 minutes timer\n"
                                "- `timer 2:45` starts a 2 hours 45 minutes timer\n"
                                "- `timer 30mn` starts a 30 minutes timer\n"
                                "- `timer 1'20` starts a 1 minutes 20 seconds timer\n"
                            ),
                        },
                        {"name": "Once a timer runs", "value": RUNNING_TIMER_HELP},
                    ],
                }
            )
        )


def get_initial_time(message, default="hour"):
    """Get initial time from message content"""
    message = message.lower()
    match = re.match(REGEX, message.lower())
    if not match:
        return
    match = match.groupdict()
    try:
        multiplier = MULTIPLIER[match.get("unit") or default]
    except KeyError:
        return
    if not match.get("unit") and match.get("separator") == "'":
        multiplier = MULTIPLIER["minute"]
    time = int(match.get("high") or 2) * multiplier
    time += float(match.get("fraction") or 0) * multiplier
    if multiplier > 1:
        time += int(match.get("low") or 0) * multiplier / 60
    return time


def main():
    """Entrypoint"""
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.DEBUG if os.getenv("DEBUG") else logging.INFO)
    client.run(os.getenv("DISCORD_TOKEN"))
