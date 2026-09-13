# Operations — laptop to gravelines

Tooling is `just` + `uv`. `just` with no recipe lists them.

| | |
|---|---|
| `just update` | `uv sync --upgrade --group dev` — the only thing that moves `uv.lock` |
| `just lint` / `just fmt` | ruff check + format (line length 100, py313) |
| `just typecheck` | `ty check --error-on-warning` |
| `just test` | `uv run pytest` |
| `just serve` | runs the bot locally, sourcing `.env` |
| `just release [minor\|major]` | clean tree required; bump, commit `release: vX.Y`, tag, build, push, `uv publish` to PyPI |
| `just clean` | drop build artifacts |

Python ≥ 3.13. One runtime dependency that matters: `discord-py-interactions` (plus `uvloop`).

## Environment

Read via `os.getenv`, no settings object. `.env` (git-ignored) exports:

- `DISCORD_TOKEN` — the bot token.
- `PYTHONOPTIMIZE` — **the dev/prod switch.** Set (production sets `1`), `__debug__` is false: commands
  register **globally** and logging is INFO. Unset, `__debug__` is true: every command is scoped to
  the debug guild `161406117686149120` and logging is DEBUG. The client runs with
  `delete_unused_application_cmds=True`, so the process syncs the application's command set to what
  it registers — never run a debug build with the production token.

## CI

`test.yml` on every PR and push to `master`: uv with Python 3.13, `uv sync --group dev`, ruff check,
ruff format check, ty, pytest. pytest exits 5 when it collects no tests, which fails the job.

The pre-commit ruff hooks are `repo: local` running `uv run ruff`: `uv.lock` is the only ruff pin.

## Deploy — today

**Host: gravelines** (`152.228.170.51`, group `krcg_gra` in `myserver`). The foundation — base
packages, SSH, UFW, observability — is `server-setup`'s.

The bot is still deployed by the **legacy `myserver` repo**, `timer-bot.yml`, through its
`python-worker` role. It is the last `python-worker` on the fleet. Deploy, from `myserver`:

```shell
ansible-playbook timer-bot.yml
```

What that leaves on the host:

- venv at `/home/lpanhaleux/projects/timer-bot/venv`, built with the host's `/usr/bin/python3` —
  **3.11 on Debian 12** — and `timer-bot` installed from **PyPI**, `state: latest`.
- unit `/etc/systemd/system/timer-bot.service`, `User=lpanhaleux`, `Restart=always`.
- **The token is an inline `Environment=` line** (vault-encrypted in the playbook, cleartext in the
  unit), next to `PYTHONOPTIMIZE=1`.
- `ExecStart` is `bash -c 'source venv/bin/activate && timer-bot'`, so journald files the logs under
  `SYSLOG_IDENTIFIER=bash`: use `journalctl -u timer-bot.service`, never `-t timer-bot`.

Sources: `myserver/timer-bot.yml` and `roles/python-worker`; `server-setup/OPERATIONS.md`.

**This deploy cannot ship the next release.** `requires-python` is `>=3.13` since the uv
modernisation; pip skips distributions whose `Requires-Python` excludes the interpreter, so `state:
latest` on the host's 3.11 resolves to 1.10 and reports success.

**A deploy restarts the bot, and a restart drops every running timer** — see
[product.md](product.md#status-2026-09-13).

## Deploy — direction

A per-app `ansible/` directory in this repo consuming the `lionel_panhaleux.server_setup`
collection, as `krcg-bot` has: uv-provided Python, a dedicated service user, the token in an env
file. `server-setup/deploy-targets.yml` already maps `lionel-panhaleux/timer` to gravelines, so
`just sync` there provisions this repo's GitHub environment with `DEPLOY_HOST` / `DEPLOY_HOST_KEY` /
`DEPLOY_SSH_KEY`. The `myserver` playbook is deleted only after the new deploy is verified running on
the host (`server-setup/OPERATIONS.md`).
