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
    r"\s*(?P<high>\d{1,2})"
    r"\s*((?P<fraction>\.\d+)|:(?P<low>\d{1,2}))?"
    r"\s*(?P<unit>h|hour|mn|min|minute|s|second)?s?\s*"
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

#: timer embed will display seconds starting frin this point int time
DISPLAY_SECONDS = 5 * 60


class Timer:
    """The timer. One active timer per channel."""

    def __init__(self, start_time, total_time, channel):
        """Initialization

        Attributes:
            start_time (int): start time in seconds, changes to adjust for pauses
            total_time (int): time until completion, never changes
            time_left (int): time left, adjusted by self.countdown()
            paused (int): If set, timer was paused at this time and waits for resume
            channel (discord.Channel): the channel this timer runs into
            message (discord.Message): the active timer embed message
            task_countdown (asyncio.Task):
                updates message embed and sends thresholds notifications
            task_reaction (asyncio.Task): waits for ⏱ or 🛑 to pause or stop
            unpause (asyncio.Future): when paused, waits for ⏱ removal to resume
            thresholds (list): list of times on which a message is sent for notification
        """
        self.start_time = start_time
        self.total_time = total_time
        self.time_left = total_time
        self.paused = None
        self.channel = channel
        self.message = None
        self.task_countdown = None
        self.task_reaction = None
        self.unpause = None
        self.thresholds = []
        for limit in THRESHOLDS:
            if total_time > limit:
                self.thresholds.append(limit)

    async def run(self):
        """Run timer
        """
        client.TIMERS[self.channel] = self
        # a pause will wait for resume then start the loop anew
        while True:
            self.task_countdown = asyncio.create_task(self.countdown())
            self.task_reaction = asyncio.create_task(
                client.wait_for(
                    "reaction_add",
                    # avoid timeouting before countdown finishes
                    timeout=self.time_left + 60,
                    # beware not to trigger on our own reaction, they are added async
                    check=lambda reaction, user: (
                        str(reaction.emoji) in ["⏱", "🛑"] and user != client.user
                    ),
                )
            )

            done, pending = await asyncio.wait(
                {self.task_countdown, self.task_reaction},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                # cancelled because of a refresh
                # reaction timeout after countdown finished
                if task.exception():
                    continue
                # "normal" finish
                if task == self.task_countdown:
                    logger.info(f"Countdown finished")
                    self.task_countdown = None
                    await self.stop()
                    break
                if task == self.task_reaction:
                    self.task_reaction = None
                    reaction, user = task.result()
                    # manual stop
                    if reaction.emoji == "🛑":
                        logger.info(f"[{user.name}] reaction stop")
                        await self.stop()
                        break
                    # pause
                    if reaction.emoji == "⏱":
                        logger.info(f"[{user.name}] reaction pause")
                        try:
                            # removes the 🛑 reaction, cancels countdown, updates embed
                            await self.pause(user)
                        # a pause over 30 minutes is considered a stop
                        except asyncio.TimeoutError:
                            logger.info(f"[{user.name}] lingering pause, stopping")
                            await self.stop()
                            break
                        except asyncio.CancelledError:
                            # if cancelled it means
                            # stop() or refresh() have been called: do not stop.
                            break
                        self.resume()
                        # restore reaction and embed, loop to recreate tasks
                        await self.message.edit(embed=self.embed())
                        await self.message.add_reaction("🛑")
            # continue if we're resuming from pause
            else:
                continue
            # all other exits use a break and return, this finishes the run
            return

    async def stop(self):
        """Terminate the timer"""
        if self.channel in client.TIMERS and client.TIMERS[self.channel] is self:
            del client.TIMERS[self.channel]
        await self._cancel_message()
        # send a notification
        # indicate remaining time so the user can setup a new timer if it was a mistake
        if self.time_left > 0:
            await self.channel.send("Stopped with " + self.time_str())
        else:
            await self.channel.send("Finished")

    async def refresh(self):
        """Deactivate the current embed message and send a new one.

        This is useful if a discussion happens in the channel
        and the embed is too high in the log.
        """
        await self._cancel_message()
        self.message = await self.channel.send(embed=self.embed())
        # If timer is ended, do not add reactions nor run
        if self.time_left < 1:
            return
        try:
            for reaction in ["⏱", "🛑"]:
                await self.message.add_reaction(reaction)
        except discord.Forbidden:
            logging.warning("Missing reaction permission")
        await self.run()

    async def _cancel_message(self):
        """Delete the current embed, resume the timer if it was paused

        This cancels all running tasks and delete the message.
        Note the timer needs to be resumed because it makes no sense to cancel
        the unpause task (waiting for the user to remove his ⏱ reaction)
        and keep a self.paused value: if refresh() is used, the user wont be able
        to unpause without pausing first...
        """
        if self.task_countdown:
            self.task_countdown.cancel()
            self.task_countdown = None
        if self.task_reaction:
            self.task_reaction.cancel()
            self.task_reaction = None
        if self.unpause:
            self.resume()
            self.unpause.cancel()
            self.unpause = None
        if self.message:
            await self.message.delete()
            self.message = None

    async def countdown(self):
        """Countdown: update embed, send notifications
        """
        while self.time_left > 0:
            # update frequency depends on time left
            if self.time_left < DISPLAY_SECONDS:
                # the is the absolute minimum because of Discord rate limitation
                await asyncio.sleep(1)
            else:
                await asyncio.sleep(30)
            self.time_left = max(
                0, self.total_time - max(0, client.loop.time() - self.start_time),
            )
            # update the embed, send a notification if we have hit a threshold
            await self.message.edit(embed=self.embed())
            if self.thresholds and self.thresholds[-1] >= self.time_left:
                await self.channel.send(self._time_str(self.thresholds.pop()))

    async def pause(self, user):
        """Pause the timer, wait for ⏱ to resume

        Note that during the pause, task_reaction is not running.
        Nobody can use a reaction but the user who paused the timer, to resume it.

        This removes the 🛑 reaction as it woud have no effect
        """
        self.paused = client.loop.time()
        if self.task_countdown:
            self.task_countdown.cancel()
        await self.message.edit(embed=self.embed())
        await self.message.remove_reaction("🛑", client.user)
        self.unpause = client.loop.create_future()
        # dicord.Client.wait_for() code
        # cannot use the method directly as we want the Future in self.unpause
        # in order to be able to cancel it if a refresh is done
        try:
            listeners = client._listeners["reaction_remove"]
        except KeyError:
            listeners = []
            client._listeners["reaction_remove"] = listeners
        listeners.append(
            (
                self.unpause,
                lambda reaction, ruser: (str(reaction.emoji) == "⏱" and ruser == user),
            )
        )
        await asyncio.wait_for(self.unpause, 1800)
        logger.info(f"[{user.name}] reaction unpause")

    def resume(self):
        """Adjust start_time and remove self.paused

        Further actions depend if it was:
        - a reaction removal to resume (we keep the same embed)
        - a refresh from `timer resume` (new embed)
        - a stop from `timer stop` (do nothing)
        """
        self.start_time += client.loop.time() - (self.paused or 0)
        self.paused = None

    def embed(self):
        """The running timer embed"""
        if self.time_left < 1:
            return discord.Embed(title="Finished")
        if self.paused:
            title = "Timer paused: " if self.paused else ""
            description = "Click the ⏱reaction again to unpause."
        else:
            title = ""
            description = "Click the ⏱reaction to pause, 🛑 to terminate."
        title += self.time_str()
        return discord.Embed.from_dict({"title": title, "description": description})

    def time_str(self):
        return self._time_str(self.time_left)

    @staticmethod
    def _time_str(time):
        """Returns a human readable string for given time (int) in seconds"""
        if time > 3600:
            return f"{int(time / 3600)}:{round(time % 3600 / 60)} remaining"
        if time > DISPLAY_SECONDS:
            return f"{int(time / 60)} minutes remaining"
        if time >= 60:
            return f"{int(time / 60)}′ {round(time % 60)}″ remaining"
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
    logger.info(f"[{prefix}] {content}")
    # timer already running in channel
    if message.channel in client.TIMERS:
        timer = client.TIMERS[message.channel]
        if content:
            if content.lower() == "stop":
                await timer.stop()
            elif content.lower() == "resume":
                await timer.refresh()
            else:
                await message.channel.send(
                    embed=discord.Embed(
                        title="Timer already running",
                        description=(
                            "- `timer` to display it\n" "- `timer stop` to terminate it"
                        ),
                    )
                )
        else:
            if timer.paused:
                await message.channel.send(
                    embed=discord.Embed(
                        title="Timer paused with " + timer.time_str(),
                        description=(
                            "- `timer resume` to display it anew\n"
                            "- `timer stop` to terminate it\n"
                        ),
                    )
                )
            else:
                await timer.refresh()
        return
    # no timer running in channel
    total_time = get_initial_time(content)
    if total_time:
        start_time = client.loop.time()
        timer = Timer(start_time, total_time, message.channel)
        await timer.refresh()
    # if parsing fails, display help
    else:
        await message.channel.send(
            embed=discord.Embed(
                title="Usage",
                description=(
                    "- `timer 2h` start a 2 hours timer\n"
                    "- `timer 2.5h` start a 2 hours 30 minutes timer\n"
                    "- `timer 2:45` start a 2 hours 45 minutes timer\n"
                    "- `timer 30mn` start a 30 minutes timer\n"
                    "- `timer` displays the current timer if there is one\n"
                    "- `timer stop` stops the current timer if there is one\n"
                ),
            )
        )


def get_initial_time(message):
    """Get initial time from message content"""
    message = message.lower()
    match = re.match(REGEX, message.lower())
    if not match:
        return
    match = match.groupdict()
    try:
        multiplier = MULTIPLIER[match.get("unit") or "hour"]
    except KeyError:
        return
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
