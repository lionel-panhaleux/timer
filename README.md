# timer

[![PyPI version](https://badge.fury.io/py/timer-bot.svg)](https://badge.fury.io/py/timer-bot)
[![Python version](https://img.shields.io/badge/python-3.8-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-blue)](https://opensource.org/licenses/MIT)
[![Code Style](https://img.shields.io/badge/code%20style-black-black)](https://github.com/psf/black)

[Discord timer bot](https://discordapp.com/oauth2/authorize?client_id=715294649836765285&scope=bot%20applications.commands).
Feel free to use it in your server.

## Notes

- When down to a seconds countdown (<5min), the bot regularly **skips a second**.
  This is normal: Discord limits the rate of message updates to one per second so there
  is no way to have a clean and precise second-by-second countdown. Even if some seconds
  are skipped on the display, the total counter is precise and fair.
