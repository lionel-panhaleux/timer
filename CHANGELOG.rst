Changelog
=========

1.7 (2024-02-06)
----------------

- Fix python 3.11 install for Debian 12


1.6 (2023-11-04)
----------------

- Fix timer updater after 1h (new Discord limitation)


1.5 (2023-11-03)
----------------

- Bump discord-py-interactions version


1.4 (2023-11-03)
----------------

- Fix timer update when finishing (display as finished, not with 1 or 2 seconds left)
- Add "secured" option so that only the owner can modify the timer
- Send message when missing permissions

1.3 (2022-12-01)
----------------

- Fix error messages when there's no timer running


1.2 (2022-08-27)
----------------

- Now works in threads and voice channel chats


1.1 (2022-08-27)
----------------

- Fix connection (no guild message access)
- Fix time boundary display (exactly 1 hour was not displayed properly)

1.0 (2022-08-27)
----------------

- V1.0
- Improve time display on boundaries (no more 1:60 or going from 5min to 4'35'')


0.12 (2022-08-27)
-----------------

- Switch to slash commands
- Use real buttons instead of reactions

0.11 (2021-03-17)
-----------------

- Fix pausing user mention


0.10 (2021-03-02)
-----------------

- Resuming a paused timer with a "timer resume" message could cause the timer to crash. Fixed it.


0.9 (2020-11-03)
----------------

- Fix pause reaction


0.8 (2020-07-22)
----------------

- Fix pause timeout (after 30mn) and `timer resume` display
- Improve help message

0.7 (2020-07-05)
----------------

- Fixed the pause timer feature


0.6 (2020-06-22)
----------------

- Mention author when finished


0.5 (2020-06-22)
----------------

- Mention timer author on thresholds and when paused by someone else


0.4 (2020-05-30)
----------------

- Fixed a bug when pause and resume where used successively
- Added "pause", "add" and "sub" commands
- Better time input parsing
- More proper hours:minutes display (with padding zeroes)


0.3 (2020-05-28)
----------------

- First version on pypi.


0.2 (2020-05-28)
----------------

- First published version.
