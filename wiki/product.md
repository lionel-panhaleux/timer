# Product

**Timer Bot** — a public Discord bot that runs one countdown per channel, shown as a single
self-updating embed with buttons, and pings whoever started it as time runs out. Anyone can invite
the hosted instance (invite link in the README); the package is also on PyPI as `timer-bot`. Its
typical use is timed rounds in a game or tournament run over Discord.

## Capabilities

All commands are subcommands of the global slash command `/timer`. Acknowledgements are ephemeral
unless stated.

**Start.** `/timer start hours [minutes] [secured]` — hours 0–24 (required), minutes 0–59, `secured`
default false. Zero total time is refused ("No time"). The bot posts the timer embed in the channel
and runs it. Works in text channels, threads and voice-channel chats. If the bot cannot send
messages there, the start acknowledgement becomes "Failed to start — requires permission to send
messages", and nothing is left in the channel.

**One timer per channel.** A start in a channel that already runs one is refused with the list of
commands for the running timer.

**The embed.** Its title is the time left:

| time left | title |
|---|---|
| over 59′ 29″ (rounds to the hour) | `H:MM remaining` |
| over 5′ 00″ | `N minutes remaining` |
| 1′ 00″ – 5′ 00″ | `M′ SS″ remaining` |
| under 1′ 00″ | `N seconds remaining` |
| paused | `Timer paused: …` |
| done | `Timer finished` |

It updates every 30 seconds, and about once a second in the last five and a half minutes — displayed
seconds skip, the count itself stays exact (see [discord.md](discord.md)). Running, it carries
**Pause** and **Stop** buttons; paused, **Resume** and **Stop**; finished, none. When Discord refuses
to edit an old embed, the bot posts a fresh one and deletes the old. When it refuses a new message —
permission revoked, channel gone — the timer ends silently, deleting its embed where Discord still
lets it.

**Pings.** The author is mentioned in the channel at every whole hour left, then at 30, 15, 5 and
1 minute left, and at zero ("time!") — however it gets there, `/timer sub` included. The marks are
recomputed from the time left whenever the timer starts or is adjusted: marks above it are skipped,
and a whole-hour mark equal to it — a timer started at exactly 2 hours — pings at once.

**Pause / resume.** `/timer pause` or the button freezes the count. A pause **auto-resumes after
30 minutes**. Pausing someone else's timer is announced publicly, mentioning its author. `/timer
resume` or the button resumes and re-posts the embed at the bottom of the channel.

**Stop.** `/timer stop` or the button ends the timer: the channel is told "Stopped with … remaining"
and the embed is deleted.

**Adjust.** `/timer add minutes` and `/timer sub minutes` (1–1440) change the time left, announce it
publicly and re-post the embed; a paused timer stays paused. Subtracting past zero finishes it.

**Display.** `/timer display` re-posts the embed at the bottom of the channel.

**Secured.** On a secured timer only its author may pause, resume, stop, add or subtract; anyone may
display it.

**No timer.** Any command but `start`, or any button, in a channel with no running timer is refused
ephemerally: "No timer running in this channel".

**Stable across deploys.** Command names, options and the buttons' `custom_id`s do not change, so
buttons on an embed posted before a restart or a deploy still answer.

## Deliberately not

- **No more than one timer per channel.**
- **No configuration** — thresholds, update cadence and the pause timeout are constants, not
  options.
- **No seconds on the display above five minutes.**
- **No database.** See [dogmas.md](dogmas.md#state).

## Status (2026-09-13)

**PyPI 1.11** — the hikari port — deployed on gravelines by this repo's `ansible/`
([operations.md](operations.md#deploy)). Not yet true of the running bot:

- **A restart drops every running timer** — timers live in process memory only. Surviving a restart
  is wanted.
