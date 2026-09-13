"""The `/timer` product at its boundary: what reaches Discord, and when.

Each test traces to a paragraph of wiki/product.md, Capabilities.
"""

import asyncio
import inspect
import itertools

import hikari
import hikari.impl
import pytest
from conftest import AUTHOR, CHANNEL, OTHER, Discord, now

import timer_bot

PING = f"<@{AUTHOR}>"


def pings(discord: Discord) -> list[tuple[float, str]]:
    return [(m.at, m.content) for m in discord.texts() if m.content and m.content.startswith(PING)]


# ########################################################################## the boundary
def test_the_stand_in_mirrors_the_rest_client():
    """A stand-in that drifts from hikari keeps the suite green while the bot breaks."""
    for name, method in inspect.getmembers(Discord, inspect.iscoroutinefunction):
        if name.startswith("_") or name in ("command", "click"):
            continue
        real = inspect.signature(getattr(hikari.impl.RESTClientImpl, name)).parameters
        for parameter in inspect.signature(method).parameters.values():
            if parameter.kind is not parameter.VAR_KEYWORD:
                assert parameter.name in real, (name, parameter.name)
                assert real[parameter.name].kind == parameter.kind, (name, parameter.name)


async def test_commands_and_buttons_keep_their_names(discord):
    """Messages posted before a deploy keep working: names, options and custom_ids hold."""
    await timer_bot.on_started(hikari.StartedEvent(app=timer_bot.bot))
    (command,) = discord.commands
    assert command.name == "timer"
    options = {
        sub.name: [(o.name, o.type, o.is_required, o.min_value, o.max_value) for o in sub.options]
        for sub in command.options
    }
    integer, boolean = hikari.OptionType.INTEGER, hikari.OptionType.BOOLEAN
    assert options == {
        "start": [
            ("hours", integer, True, 0, 24),
            ("minutes", integer, False, 0, 59),
            ("secured", boolean, False, None, None),
        ],
        "pause": [],
        "resume": [],
        "stop": [],
        "add": [("minutes", integer, True, 1, 1440)],
        "sub": [("minutes", integer, True, 1, 1440)],
        "display": [],
    }
    assert discord.guild == (timer_bot.DEBUG_GUILD if __debug__ else hikari.UNDEFINED)
    await discord.command("start", hours=1)
    assert discord.embed().buttons == ["pause", "stop"]
    await discord.click("pause")
    assert discord.embed().buttons == ["resume", "stop"]


# ################################################################################# start
async def test_start_posts_the_timer(discord):
    await discord.command("start", hours=1, minutes=30)
    assert discord.response().content == "Starting Timer"
    assert discord.response().ephemeral
    assert discord.embed().title == "1:30 remaining"
    assert discord.embed().buttons == ["pause", "stop"]
    assert not pings(discord)


async def test_start_refuses_no_time(discord):
    await discord.command("start", hours=0, minutes=0)
    assert discord.response().title == "No time"
    assert discord.response().ephemeral
    assert not discord.messages
    await discord.command("start", hours=0, minutes=6)
    assert discord.embed().title == "6 minutes remaining"


async def test_start_in_a_thread(discord):
    """A thread is never in hikari's cache: the channel comes from the payload alone."""
    thread = CHANNEL + 1
    await discord.command("start", channel=thread, channel_type=11, hours=0, minutes=10)
    assert discord.embed(thread).title == "10 minutes remaining"
    await discord.command("pause", channel=thread)
    assert discord.embed(thread).title == "Timer paused: 10 minutes remaining"


async def test_start_without_permission_to_send(discord):
    discord.refuse["create_message"] = 1
    await discord.command("start", hours=1)
    assert discord.response().content == (
        "**Failed to start**\nTimer bot requires permission to send messages"
    )
    assert not discord.channel()
    await discord.command("start", hours=1)
    assert discord.embed().title == "1:00 remaining"


async def test_start_in_a_busy_channel_is_refused(discord):
    await discord.command("start", hours=0, minutes=10)
    await discord.command("start", user=OTHER, hours=2)
    assert discord.response().title == "Timer already running"
    assert discord.response().description == timer_bot.RUNNING_TIMER_HELP
    assert discord.response().ephemeral
    assert discord.embed().title == "10 minutes remaining"
    await asyncio.sleep(10 * 60 + 5)
    assert discord.embed().title == "Timer finished"
    assert not timer_bot.TIMERS


async def test_timers_in_other_channels_run_apart(discord):
    other = CHANNEL + 2
    await discord.command("start", hours=0, minutes=10)
    await discord.command("start", channel=other, hours=0, minutes=20)
    await asyncio.sleep(10 * 60 + 5)
    assert discord.embed().title == "Timer finished"
    assert discord.embed(other).title == "10 minutes remaining"
    await discord.command("pause", channel=other)
    assert discord.embed(other).title.startswith("Timer paused")


# ################################################################################# embed
def test_time_display():
    """Property-style: every title reads within its display's precision of the time left."""
    for time in (s + fraction for s in range(25 * 3600) for fraction in (0, 0.49, 0.5)):
        title = timer_bot.time_str(time)
        if time > 3569:
            hours, minutes = title.removesuffix(" remaining").split(":")
            assert len(minutes) == 2
            assert abs(int(hours) * 3600 + int(minutes) * 60 - time) <= 30
        elif time > timer_bot.DISPLAY_SECONDS:
            assert title.endswith(" minutes remaining")
            assert abs(int(title.split()[0]) * 60 - time) <= 30
        elif "′" in title:
            minutes, seconds_ = title.removesuffix("″ remaining").split("′ ")
            assert 1 <= int(minutes) <= 5 and len(seconds_) == 2
            assert abs(int(minutes) * 60 + int(seconds_) - time) <= 0.5
        elif time > 0:
            assert title.endswith(" seconds remaining")
            assert abs(int(title.split()[0]) - time) <= 0.5
        else:
            assert title == "time!"


async def test_embed_update_cadence(discord):
    await discord.command("start", hours=0, minutes=15)
    start = now()
    await asyncio.sleep(15 * 60 + 5)
    times = [t - start for t, _ in discord.embed().updates]
    gaps = [(b, b - a) for a, b in itertools.pairwise(times)]
    slow = [gap for at, gap in gaps if at < 15 * 60 - (timer_bot.DISPLAY_SECONDS + 30)]
    fast = [gap for at, gap in gaps if at > 15 * 60 - timer_bot.DISPLAY_SECONDS]
    assert slow and all(gap <= 30.01 for gap in slow)
    assert max(slow) == pytest.approx(30)
    assert fast and all(gap <= 1.11 for gap in fast)
    assert discord.embed().title == "Timer finished"
    assert discord.embed().buttons == []


async def test_refused_edit_posts_a_fresh_embed(discord):
    """Discord caps edits on messages older than an hour (30046)."""
    await discord.command("start", hours=2)
    old = discord.embed()
    discord.refuse["edit_message"] = 1
    await asyncio.sleep(31)
    assert old.deleted
    assert discord.embed() is not old
    assert discord.embed().buttons == ["pause", "stop"]
    await asyncio.sleep(31)
    assert not old.updates[1:]
    assert len(discord.embed().updates) == 2


# ################################################################################# pings
async def test_pings_on_every_mark(discord):
    """Started at exactly 2 hours: the 2-hour mark pings at once."""
    await discord.command("start", hours=2)
    start = now()
    await asyncio.sleep(2 * 3600 + 5)
    expected = [
        (0, "2:00 remaining"),
        (3600, "1:00 remaining"),
        (5400, "30 minutes remaining"),
        (6300, "15 minutes remaining"),
        (6900, "5′ 00″ remaining"),
        (7140, "1′ 00″ remaining"),
        (7200, "time!"),
    ]
    got = [(t - start, content) for t, content in pings(discord)]
    assert [content for _, content in got] == [f"{PING} {text}" for _, text in expected]
    for (at, _), (expected_at, _) in zip(got, expected):
        assert at == pytest.approx(expected_at, abs=0.1)
    assert all(m.mentions == [AUTHOR] for m in discord.texts() if m.content.startswith(PING))
    assert discord.embed().title == "Timer finished"


async def test_marks_follow_an_adjustment(discord):
    """Marks above the time left are skipped, and recomputed when time is added."""
    await discord.command("start", hours=0, minutes=20)
    await asyncio.sleep(60)
    assert not pings(discord)
    await discord.command("add", minutes=60)
    start = now()
    await asyncio.sleep(19 * 60 + 1)
    assert [content for _, content in pings(discord)] == [f"{PING} 1:00 remaining"]
    assert pings(discord)[0][0] - start == pytest.approx(19 * 60, abs=0.1)
    await asyncio.sleep(30 * 60)
    assert pings(discord)[-1][1] == f"{PING} 30 minutes remaining"


# ########################################################################## pause/resume
async def test_pause_and_resume(discord):
    await discord.command("start", hours=0, minutes=10)
    await asyncio.sleep(60)
    await discord.command("pause")
    assert discord.response().content == "Timer paused"
    assert discord.response().ephemeral
    assert discord.embed().title == "Timer paused: 9 minutes remaining"
    assert discord.embed().buttons == ["resume", "stop"]
    await asyncio.sleep(20 * 60)
    assert discord.embed().title == "Timer paused: 9 minutes remaining"
    paused = discord.embed()
    await discord.click("resume")
    assert discord.response().content == "Timer resumed"
    assert paused.deleted
    assert discord.embed().title == "9 minutes remaining"
    assert discord.embed().buttons == ["pause", "stop"]
    resumed = now()
    await asyncio.sleep(9 * 60 + 2)
    assert discord.embed().title == "Timer finished"
    assert pings(discord)[-1][0] - resumed == pytest.approx(9 * 60, abs=0.1)


async def test_pause_resumes_on_its_own_after_30_minutes(discord):
    await discord.command("start", hours=0, minutes=10)
    await discord.click("pause")
    paused = now()
    await asyncio.sleep(30 * 60 - 1)
    assert discord.embed().title == "Timer paused: 10 minutes remaining"
    await asyncio.sleep(2)
    assert discord.embed().title == "10 minutes remaining"
    await asyncio.sleep(10 * 60)
    assert pings(discord)[-1][1] == f"{PING} time!"
    assert pings(discord)[-1][0] - paused == pytest.approx(40 * 60, abs=0.1)


async def test_pausing_someone_elses_timer_is_announced(discord):
    await discord.command("start", hours=1)
    await discord.click("pause", user=OTHER)
    response = discord.response()
    assert not response.ephemeral
    assert response.content == f"<@{AUTHOR}> timer paused by <@{OTHER}>"
    assert AUTHOR in response.mentions


# ################################################################################## stop
@pytest.mark.parametrize("stop", ["command", "button"])
async def test_stop(discord, stop):
    await discord.command("start", hours=0, minutes=10)
    await asyncio.sleep(60)
    embed = discord.embed()
    await (discord.command("stop") if stop == "command" else discord.click("stop"))
    assert discord.response().content == "Timer stopped"
    assert discord.response().ephemeral
    assert embed.deleted
    assert not discord.embeds()
    assert [m.content for m in discord.channel()] == ["Stopped with 9 minutes remaining"]
    await asyncio.sleep(3600)
    assert [m.content for m in discord.channel()] == ["Stopped with 9 minutes remaining"]
    assert not timer_bot.TIMERS


# ################################################################################ adjust
async def test_add_reposts_and_announces(discord):
    await discord.command("start", hours=0, minutes=10)
    old = discord.embed()
    await discord.command("add", minutes=5)
    assert discord.response().content == "Time added (5min)"
    assert not discord.response().ephemeral
    assert old.deleted
    assert discord.embed().title == "15 minutes remaining"


async def test_adjusting_a_paused_timer_keeps_it_paused(discord):
    await discord.command("start", hours=0, minutes=10)
    await discord.command("pause")
    await discord.command("sub", minutes=3)
    assert discord.response().content == "Time substracted (3min)"
    assert not discord.response().ephemeral
    assert discord.embed().title == "Timer paused: 7 minutes remaining"
    assert discord.embed().buttons == ["resume", "stop"]


async def test_subtracting_past_zero_finishes(discord):
    await discord.command("start", hours=0, minutes=10)
    await discord.command("sub", minutes=30)
    assert discord.embed().title == "Timer finished"
    assert not timer_bot.TIMERS


# ############################################################################### display
async def test_display_reposts_at_the_bottom(discord):
    await discord.command("start", hours=1)
    old = discord.embed()
    discord.messages.append(  # someone talks in the channel
        type(old)(
            id=hikari.Snowflake(1),
            channel=CHANNEL,
            content="hi",
            title=None,
            buttons=[],
            mentions=[],
            at=now(),
        )
    )
    await discord.command("display")
    assert discord.response().content == "Timer displayed"
    assert discord.response().ephemeral
    assert old.deleted
    assert discord.channel()[-1].title == "1:00 remaining"


# ############################################################################### secured
async def test_secured_timer(discord):
    await discord.command("start", hours=1, secured=True)
    refusals = {
        "pause": "pause",
        "resume": "resume",
        "stop": "stop",
        "add": "modify",
        "sub": "modify",
    }
    for subcommand, verb in refusals.items():
        options = {"minutes": 5} if subcommand in ("add", "sub") else {}
        await discord.command(subcommand, user=OTHER, **options)
        assert discord.response().content == (
            f"This is a secured timer, only the owner can {verb} it."
        )
        assert discord.response().ephemeral
    await discord.click("pause", user=OTHER)
    assert discord.response().content == "This is a secured timer, only the owner can pause it."
    assert discord.embed().title == "1:00 remaining"
    await discord.command("display", user=OTHER)
    assert discord.response().content == "Timer displayed"
    await discord.command("pause")
    assert discord.embed().title == "Timer paused: 1:00 remaining"


async def test_no_timer_in_the_channel(discord):
    """Including a button on an embed that outlived its timer, e.g. across a restart."""
    for subcommand in ("pause", "resume", "stop", "display"):
        await discord.command(subcommand)
        assert discord.response().content == timer_bot.NO_TIMER
        assert discord.response().ephemeral
    await discord.command("add", minutes=5)
    assert discord.response().content == timer_bot.NO_TIMER
    for button in ("pause", "resume", "stop"):
        await discord.click(button)
        assert discord.response().content == timer_bot.NO_TIMER
