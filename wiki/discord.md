# Discord — the platform we run on

Standing knowledge of Discord and of `hikari`, scoped to what a single-message countdown bot
touches. Every claim names its source; retrieved 2026-09-13 against locked `hikari` 2.6.0. Re-check
sources in `/upkeep`, not code.

## Interactions

- **An interaction must get its initial response within 3 seconds**, and its token is valid for
  **15 minutes**; follow-ups and edits through the interaction only work inside that window.
  [receiving-and-responding](https://docs.discord.com/developers/interactions/receiving-and-responding)
  — so anything the bot does to a timer message *later* (the countdown runs for up to 24h+) goes
  through the channel API as the bot (`bot.rest`), never through the interaction.
- **Ephemeral** responses (the `EPHEMERAL` message flag) are visible only to the invoking user.
  [same page]
- A button carries a developer-chosen **`custom_id`**; the interaction reports which one was clicked.
  [same page] The interaction arrives whatever process posted the button, so dispatching on the
  `custom_id` alone **keeps old buttons working after a restart or a deploy**. [same page; exercised
  by `tests/test_timer.py::test_no_timer_in_the_channel`]

## Slash commands

- **A bulk overwrite replaces the whole set**: `PUT` of the application's commands (hikari
  `set_application_commands`) deletes every command not in the list, globally or — given a guild —
  in that guild only. Guild commands are separate from global ones: a command in both shows twice
  there. [application-commands](https://docs.discord.com/developers/interactions/application-commands#bulk-overwrite-global-application-commands)
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

## hikari traps

- **No user mention notifies unless asked.** With `user_mentions` left undefined, `create_message` and
  `create_initial_response` send `allowed_mentions` with user mentions disabled: `<@id>` renders, and
  pings no one. Pass the ids. [hikari 2.6 source, `internal/mentions.py`]
- **`interaction.channel_id` is a payload field**, always present; no cache lookup is needed to
  answer or to write, so an uncached thread behaves like any channel. `hikari.Snowflake` is a plain
  `int`: key maps by id. [hikari 2.6 source, `impl/entity_factory.py`, `snowflakes.py`]
- **Client errors are `hikari.ClientHTTPResponseError`** — `BadRequestError` (400, incl. 30046),
  `ForbiddenError` (403), `NotFoundError` (404); 5xx is `InternalServerError`, outside it.
  [hikari 2.6 source, `errors.py`]
- **`GatewayBot.__init__` parses the token**, so importing the module needs a well-formed one; the
  test conftest assembles a fake. [hikari 2.6 source, `impl/gateway_bot.py`]
