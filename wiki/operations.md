# Operations — laptop to gravelines

Tooling is `just` + `uv`. `just` with no recipe lists them.

| | |
|---|---|
| `just update` | `uv sync --upgrade --group dev` — the only thing that moves `uv.lock` |
| `just lint` / `just fmt` | ruff check + format (line length 100, py313) |
| `just typecheck` | `ty check --error-on-warning` |
| `just test` | `uv run pytest` |
| `just serve` | runs the bot locally, sourcing `.env` |
| `just release [minor\|major]` | clean tree required; bump, commit `release: vX.Y`, tag, build, push, then `just publish` |
| `just publish` | upload `dist/` to PyPI with the token in `~/.pypi_token` — `uv publish` never reads `~/.pypirc`. Re-run it alone when a release fails after the push |
| `just deploy [version]` | converge a PyPI release onto gravelines — [Deploy](#deploy) |
| `just clean` | drop build artifacts |

The pre-commit ruff hooks are `repo: local` running `uv run ruff`: `uv.lock` is the only ruff pin.

Python ≥ 3.13. One runtime dependency: `hikari`.

## Environment

Read via `os.environ`, no settings object; a missing `DISCORD_TOKEN` fails at import, naming it.
`.env` (git-ignored) exports:

- `DISCORD_TOKEN` — the bot token.
- `PYTHONOPTIMIZE` — **the dev/prod switch.** Set (production sets `1`), `__debug__` is false: commands
  register **globally** and logging is INFO. Unset, `__debug__` is true: every command is scoped to
  the debug guild `161406117686149120` and logging is DEBUG. On start the bot bulk-overwrites its
  scope's command set with `/timer` ([discord.md](discord.md#slash-commands)). A debug build with the
  production token leaves the global command alone but shows `/timer` twice in the debug guild: use
  a separate dev application.

## CI

`test.yml` on every PR and push to `master`: uv with Python 3.13, `uv sync --group dev`, ruff check,
ruff format check, ty, pytest. pytest exits 5 when it collects no tests, which fails the job.

## Deploy

**Host: gravelines** (`152.228.170.51`). The foundation — base packages, SSH, UFW, observability —
is `server-setup`'s. The deploy is `ansible/deploy.yml`, shaped like krcg-bot's on the same host, run
from the laptop:

```shell
just deploy        # the version in pyproject.toml
just deploy 1.10   # any major.minor on PyPI: a rollback
```

Ansible refuses a shell whose stdio is non-blocking — an agent's shell, or `!` in Claude Code — with
"Ansible requires blocking IO". Give it a pseudo-terminal: `script -q /dev/null just deploy 1.10`.

It installs `timer-bot==<version>` **from PyPI**: what runs answers to a release, and no path ships
the working tree. There is no CI deploy ([dogmas.md](dogmas.md#commits-releases-deploys)), so this
repo is not in `server-setup/deploy-targets.yml` and has no GitHub environment.

`ansible-core` is the `deploy` dependency group (`uv run --group deploy`), out of `dev` so CI never
installs it. The play uses only `ansible.builtin` — the `server_setup` collection's roles are `nginx_site` and
`postgres_db`, neither of which a bot needs. It connects as `deploy` (`DEPLOY_USER` overrides), which
needs passwordless sudo.

What a converge leaves on the host:

- `uv` at `/usr/local/bin/uv`, installed only if missing — krcg-bot runs off the same one — and
  **Python 3.13 fetched by uv** into `/opt/uv/python`; the host's own is 3.11 (Debian 12).
- system user `timer-bot`; venv `/opt/timer-bot/venv`.
- the token in `/etc/timer-bot/env` (`root:timer-bot`, 0640), read by `EnvironmentFile=`; the unit
  itself carries only `PYTHONOPTIMIZE=1`. Neither file is written with a backup, so a rotation leaves
  no old token behind.
- unit `/etc/systemd/system/timer-bot.service`, `Restart=always`, `ExecStart` the venv's `timer-bot`:
  `journalctl -u timer-bot.service` or `-t timer-bot`. `server-setup`'s Alloy ships the whole journal
  to Grafana Cloud Loki, labelled `unit="timer-bot.service"` and `tag="timer-bot"`: nothing here
  configures log collection.

**A restart drops every running timer** ([product.md](product.md#status-2026-09-13)). A converge
restarts only when the installed version, the token or the unit changes, then checks 20 seconds later
that the unit is still the same run — `Restart=always` makes a crash loop pass through `active`.

### Secrets

`ansible/vault.yml` holds `discord_token`, committed ansible-vault-encrypted; this repo is public, so
a pre-commit hook refuses it without the vault header. The vault password is committed
age-encrypted as `ansible/secrets/vault-pass.age`, readable by the public keys in
`ansible/secrets/age-recipients.txt`. `ansible.cfg` reads it from the git-ignored
`ansible/.vault_pass` (`age` must be installed on the laptop):

```shell
age -d -i ~/.ssh/<key> -o ansible/.vault_pass ansible/secrets/vault-pass.age
```

Adding a recipient: decrypt, append the public key, then
`age -R ansible/secrets/age-recipients.txt -o ansible/secrets/vault-pass.age < ansible/.vault_pass`.
Removing one only stops future decrypts; revoking for cause means a new vault password and
re-encrypting `vault.yml` with it.

### Until the cutover

The host still runs 1.10 from the **legacy `myserver` repo**'s `timer-bot.yml` (`python-worker`
role): venv `/home/lpanhaleux/projects/timer-bot/venv` on the host's 3.11, `User=lpanhaleux`, the
token an inline `Environment=` line in the unit, logs under `SYSLOG_IDENTIFIER=bash`. pip skips a
`>=3.13` release there and reports success, so nothing after 1.10 can ship through it. Both deploys
write the same unit name: systemd stops the old process before starting the new one, never two
gateways on one token.
