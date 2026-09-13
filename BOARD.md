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

- Refresh the tooling: `uv_build>=0.12.13,<0.13`; `just update` to current ruff; the pre-commit ruff hooks become `repo: local` running `uv run ruff`, so `uv.lock` is the only ruff pin, and `pre-commit-hooks` goes to v6.0.0; add `ty` to the dev group with `just typecheck` (`ty check --error-on-warning`) and a CI step; `astral-sh/setup-uv@v10`, `actions/checkout@v7`. Done: `just lint` green, `uv.lock` holds uv_build 0.12.x and ruff 0.16.x, `just typecheck` runs locally and in `test.yml` (it may stay red on interactions.py code until the port below). Doc-impact: `operations.md`; `CLAUDE.md`, `/ship` and `egress-reviewer` name `just typecheck`.
- Port the bot from interactions.py to raw `hikari.GatewayBot`, as krcg-bot does (overturns `wiki/dogmas.md` framework idioms), keeping slash-command names, options and button `custom_id`s (`pause`/`resume`/`stop`) identical so messages posted before the deploy keep working; land the boundary test suite with it (`wiki/dogmas.md#testing`); drop `discord-py-interactions` and `uvloop`. The interactions.py bugs die with it: a second `/timer start` in a busy channel runs a second timer, and an uncached thread channel crashes commands (`wiki/discord.md`, interactions.py traps). Done: `just test` and `just typecheck` green; every `product.md` Capabilities paragraph has a boundary test, including a refused second start in a busy channel and a command run in a thread. Doc-impact: `dogmas.md` (framework, errors, testing), `discord.md` (traps section), `operations.md`, `product.md` Status, `CLAUDE.md`.
- Move the deploy into this repo: a per-app `ansible/` consuming the server-setup collection, as krcg-bot did (`wiki/operations.md#deploy--direction`), which is also what lets a `>=3.13` release install. Done: `timer-bot.service` on gravelines runs this repo's play under Python 3.13; `timer-bot.yml` and `roles/python-worker` deleted from `myserver`; the `myserver` table in `server-setup/OPERATIONS.md` updated. Doc-impact: `operations.md`, `product.md` Status.
- Survive a restart: running timers (channel, author, deadline or paused remainder, secured, embed message, pending pings) persist to a local state file and resume on startup (`wiki/dogmas.md#state`). Done: a boundary test stops the bot mid-timer, starts a new one on the same state file, and the timer ends on time with its pings. Doc-impact: `product.md`, `dogmas.md#state`, `operations.md` (the state file on the host).
- Answer GitHub issue #2 ("tried to self host but doesnt work", open since 2022-11-30). Done: the issue has a reply and is closed.
- Refresh the README badges — they claim Python 3.8 and black; it is 3.13 and ruff. Done: badges match `pyproject.toml`.

<!-- cycles-since-upkeep: 0 -->
