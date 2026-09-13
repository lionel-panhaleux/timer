# Discord — the platform we run on

Standing knowledge of Discord and of `discord-py-interactions` (imported as `interactions`), scoped to
what a single-message countdown bot touches. Every claim names its source; retrieved 2026-09-13
against locked `discord-py-interactions` 5.16.0. Re-check sources in `/upkeep`, not code.

## Interactions

- **An interaction must get its initial response within 3 seconds**, and its token is valid for
  **15 minutes**; follow-ups and edits through the interaction only work inside that window.
  [receiving-and-responding](https://docs.discord.com/developers/interactions/receiving-and-responding)
  — so anything the bot does to a timer message *later* (the countdown runs for up to 24h+) goes
  through the channel API as the bot, never through `ctx`.
- **Ephemeral** responses (the `EPHEMERAL` flag, `ephemeral=True`) are visible only to the invoking
  user. [same page]
- A button carries a developer-chosen **`custom_id`**; the interaction reports which one was clicked.
  [same page] In interactions.py, `@component_callback("<custom_id>")` handles it and **keeps working
  after a restart** — a button on an old message still reaches the new process.
  [interactions.py, Components guide](https://github.com/interactions-py/interactions.py/blob/stable/docs/src/Guides/05%20Components.md)

## Slash commands

- Commands are **global** by default; `debug_scope` on the client scopes every command to one guild
  instead. [interactions.py, Creating Commands guide](https://github.com/interactions-py/interactions.py/blob/stable/docs/src/Guides/03%20Creating%20Commands.md)
- **Slash commands live on Discord, not on the host.** Stopping the process does not remove them;
  only deleting the application or clearing its global commands does.
  [server-setup `OPERATIONS.md`, "Retiring a service"]

## Rate limits and errors

- **Global limit: 50 requests per second** per bot. **Per-route** limits also apply, computed
  separately per top-level resource (`channel_id`, `guild_id`), so each channel has its own message
  bucket. [rate-limits](https://docs.discord.com/developers/topics/rate-limits)
- **Invalid requests** (401, 403, 429) are capped at **10,000 per 10 minutes** per IP; beyond it the
  IP is temporarily banned from the API. [same page] A bot looping on a missing permission is how
  this happens.
- **Error 30046** — "Maximum number of edits to messages older than 1 hour reached". The budget is
  not published. [opcodes-and-status-codes](https://docs.discord.com/developers/topics/opcodes-and-status-codes)
  A countdown edited every 30 seconds hits it once its message is an hour old.
- **Error 50001** "Missing access", **50013** "You lack permissions to perform that action" — the
  bot lacks access to the channel or permission to send there. [same page]
- **One message update per second** is the operating assumption behind the seconds countdown, and
  why displayed seconds skip. Discord does not publish it as such; the source is this project's
  README.

## interactions.py traps

- **A Discord object and its id compare equal but hash differently.** `SnowflakeObject.__eq__`
  compares ids, `__hash__` is `id << 32`, while `Snowflake` is a plain `int` subclass. `channel ==
  channel.id` is true, yet `channel.id in {channel: …}` is false. Never mix the two as dict keys.
  [interactions.py 5.16 source, `models/discord/snowflake.py`]
- **`ctx.channel` is a cache lookup**, not a payload field: `client.cache.get_channel(channel_id)`
  (DM channel when there is no guild). It is `None` when the channel is not cached, never
  `MISSING`, and it is **read-only** — a property with no setter, so `ctx.channel = …` raises
  `AttributeError`; resolve into a local instead (`await client.fetch_channel(ctx.channel_id)`).
  [interactions.py 5.16 source, `models/internal/context.py`, `client/smart_cache.py`]
- `interactions.errors` is `interactions.client.errors`; every library-side HTTP failure is a
  `LibraryException` subclass. [interactions.py 5.16 source]
