# Board

What must change. The goal is zero. **Completion is deletion** — no closed state, no archive; git
history is the record. Context lives in [`wiki/`](wiki/index.md), never here: a line that cannot be
completed is documentation, and belongs on a wiki page instead.

**Order is priority**, and priority is decided by these rules, top down:

1. **Blocks someone else** — another person, another repo, another line.
2. **User-visible breakage.**
3. **User-visible feature.**
4. **Internal cleanup.**

Ties break to the smaller line. An item waiting on someone is not a state: it is a dated
follow-up ("chase @someone, 12 Oct"), owned by whoever wrote it.

---

- Stand up the boundary test suite (`wiki/dogmas.md#testing`: Discord replaced by a stand-in at the bot's boundary, property tests for the time display and thresholds) and fix what it catches first: a second `/timer start` in a busy channel starts a second timer, because `TIMERS` is keyed by channel object but `timer_start` looks up `ctx.channel_id` (`wiki/discord.md`, interactions.py traps) — take the dead `is MISSING` channel branch and the dead `asyncio.TimeoutError` handler in `Timer.run` with it. Done: `just test` exits 0 on tests tracing to `product.md` claims, including a refused second start. Doc-impact: `operations.md` (the test harness), `product.md` Status.
- Resolve the channel when `ctx.channel` is `None` (an uncached thread or voice-channel chat) in every `/timer` command and button, not only `start`. Done: a boundary test drives each command with an uncached channel and gets the normal answer. Doc-impact: none — `product.md` already claims threads and voice-channel chats.
- Move the deploy into this repo: a per-app `ansible/` consuming the server-setup collection, as krcg-bot did (`wiki/operations.md#deploy--direction`), which is also what lets a `>=3.13` release install. Done: `timer-bot.service` on gravelines runs this repo's play under Python 3.13; `timer-bot.yml` and `roles/python-worker` deleted from `myserver`; the `myserver` table in `server-setup/OPERATIONS.md` updated. Doc-impact: `operations.md`, `product.md` Status.
- Survive a restart: running timers (channel, author, deadline or paused remainder, secured, embed message, pending pings) persist to a local state file and resume on startup (`wiki/dogmas.md#state`). Done: a boundary test stops the bot mid-timer, starts a new one on the same state file, and the timer ends on time with its pings. Doc-impact: `product.md`, `dogmas.md#state`, `operations.md` (the state file on the host).
- Answer GitHub issue #2 ("tried to self host but doesnt work", open since 2022-11-30). Done: the issue has a reply and is closed.
- Refresh the README badges — they claim Python 3.8 and black; it is 3.13 and ruff. Done: badges match `pyproject.toml`.

<!-- cycles-since-upkeep: 0 -->
