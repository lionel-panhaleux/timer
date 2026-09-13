# Dogmas

Paradigms chosen by the human. Ingress challenges an incoming ask against this page; egress checks
the landed change against it. Overturning one is valid work; violating one silently is not.
Observed in the code and confirmed by interview, 2026-09-13.

## Code

**Tight, local, KISS.** No patterns, abstractions or indirection for elegance's sake — they must earn
their keep. Don't write for a human reader's comfort; keep it terse for agentic workers.

**One module.** The whole bot is `src/timer_bot/__init__.py`. Extract a module only behind an
interface much narrower than what it hides. Layering ceremony — clean-arch, hexagonal — is an
anti-pattern here: it mass-produces shallow modules, which are pure token cost and misuse surface.

**KISS means hazard-avoidance, not small diffs.** Big rewrites are cheap; the coding loop is agentic
and rewrites fast. What is expensive is *hazard* — non-local interdependency, behaviour not evident
where it lives, traps for a future agent without today's context. Prefer the design a fresh agent
can understand from the files in front of it. The amount of code needing a rewrite is never a reason
to defer.

**Repetition over false abstraction.** Similar-looking but causally unrelated code stays repeated.
Never factor on resemblance.

**Comments are for traps only.** The wiki holds the why, the code shows the how. A comment is
justified only by a subtle non-local constraint invisible at the point of reading. No narration, no
changelogs, **no TODOs** — discovered work goes through ingress or gets done now.

**Raw hikari, no command framework**, as krcg-bot. A `hikari.GatewayBot` with no gateway intents
and `bot.listen()` listeners; the one `/timer` command is built as a builder and PUT on start;
dispatch is a dict from subcommand name or button `custom_id` to handler; every channel write goes
through `bot.rest` by id. `os.environ` at point of use, no settings object. `__debug__` is the
dev/prod switch — see [operations.md](operations.md).

## Errors

**Discord refusing a channel write is logged, and the bot carries on**: a
`hikari.ClientHTTPResponseError` (any 4xx) from an edit, a delete or a send is logged at INFO and
worked around (a fresh message, a user-facing sentence, or the timer ends). A refusal of the
user's request is a `CommandFailed`, answered ephemerally. Anything else is raised — except in a
timer's own task, where nothing would catch it: there it is logged with its traceback and the
timer ends. One timer's failure never takes down the others.

## State

**State that must survive a restart lives in a local file, never a database server.** A full
database is out of proportion for a handful of running timers. *(Interview, 2026-09-13.)* Until that
lands, timers are in process memory only.

## Testing

**Few tests, high coverage of behaviour.** Test what the product does at its boundary — the `/timer`
commands and buttons, the embed and pings they produce, the failure modes that matter — never how it
does it. Agents don't make local mistakes, they make non-local ones: unit tests of internals
calcify implementation and tax every change, while integration and non-regression tests survive
refactors.

- A test is the executable slice of this wiki: each traces to a claim in
  [product.md](product.md). One that maps to no claim is evicted.
- **Mocks of our own code are banned.** Discord and the clock are the two dependencies with no local
  real thing. Discord: **a stand-in for `bot.rest`** records what was sent and scripts refusals, and a
  test asserts it mirrors `RESTClientImpl`'s signatures; interactions are Discord's own JSON payloads
  deserialized by hikari and sent through `bot.dispatch`, so handlers receive the real objects by
  their real subscription. The clock: tests run on **an event
  loop whose clock jumps** to the next scheduled callback, so a two-hour timer runs in milliseconds
  and on time. Never patch the bot's own functions, and don't build a fake Discord server.
- Exception: property-style tests for the time display and threshold arithmetic — the hazardous
  invariant here; most of this bot's past fixes were display-boundary bugs.
- **Weakening or deleting a test is an egress rejection** unless the wiki-declared behaviour changed.

`just test` must pass on every landing. *(Adopted 2026-09-13.)*

## Dependencies

Prefer what is already here, then a few lines, then a dependency. `uv.lock` is the pin; only
`just update` moves it.

## Records

**No changelog.** Git history and the release tags are the record; the bot's users use the hosted
instance, not release notes. *(Interview, 2026-09-13.)*

## Commits, releases, deploys

**Trunk-based**: commit straight to `master`, no feature branches. Two or three agents may work
parallel board lines on `master` — each claims its line, stays aware of siblings, keeps to its own
commits; imperfect commit isolation is acceptable when files overlap.

Describe the change itself in the message. When a commit fixes a GitHub issue, close it with a
`Fixes #N` line just above the trailers.

**`just release` is the only way a version moves** (`major.minor`, default minor bump). Releasing
publishes to PyPI and deploying restarts the public bot: both are the human's call.

**Deploys move to this repo.** The legacy `myserver` playbook goes; the bot gets a per-app `ansible/`
directory consuming the `lionel_panhaleux.server_setup` collection, as krcg-bot did.
*(Interview, 2026-09-13.)*

## Human inflexion points

Interrupt the human only for: a dogma or paradigm choice (short option set plus a recommendation), an
irreversible or outward-facing action (push, release, deploy, answering an issue), a genuine change to
product scope, or an egress deadlock after two rounds. Everything else proceeds. HitL effort goes
into the harness, not the code — the ratchet turns a correction into a standing rule.
