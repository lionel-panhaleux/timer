# timer

[![PyPI version](https://badge.fury.io/py/timer-bot.svg)](https://badge.fury.io/py/timer-bot)
[![Python version](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-blue)](https://opensource.org/licenses/MIT)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

[Discord timer bot](https://discordapp.com/oauth2/authorize?client_id=715294649836765285&scope=bot%20applications.commands).
Feel free to use it in your server (click the link).

## Self-hosting

Create an application in the [Discord Developer Portal](https://discord.com/developers/applications),
copy its bot token, and invite it with the `bot` and `applications.commands` scopes. Then, with
Python 3.13+:

```shell
pip install timer-bot
DISCORD_TOKEN=<token> PYTHONOPTIMIZE=1 timer-bot
```

`PYTHONOPTIMIZE=1` is required: without it, `/timer` does not register globally.
Running timers are saved to `timers.json` in `STATE_DIRECTORY`, or in the working directory if it is
not set.

## Notes

- When down to a seconds countdown (<5min), the bot regularly **skips a second**.
  This is normal: Discord limits the rate of message updates to one per second so there
  is no way to have a clean and precise second-by-second countdown. Even if some seconds
  are skipped on the display, the total counter is precise and fair.
