# Deploy cutover — myserver to `ansible/`

Contract for the top board line. Dies with it.

## Phase 1 — landed

`ansible/deploy.yml`, `just deploy`, the vault guard, `wiki/operations.md#deploy`. Syntax-checked,
never converged.

## Phase 2 — the human, in order

All from the repo root. Nothing here should put the token in a terminal log you keep.

1. **Bootstrap the vault.** The token is the one the bot runs on today, in `myserver/timer-bot.yml`'s
   vault — not `systemctl cat` on the host, which prints it. Untested (Ansible will not run in the
   agent's shell): from `myserver`,
   `yq '.[0].roles[0].pw_env.DISCORD_TOKEN' timer-bot.yml | ansible-vault decrypt --output -`.
   ```shell
   cd ansible
   head -c 32 /dev/urandom | base64 > .vault_pass
   age -R secrets/age-recipients.txt -o secrets/vault-pass.age < .vault_pass
   uv run --group deploy ansible-vault create vault.yml    # discord_token: <token>
   ```
   Commit `ansible/vault.yml` and `ansible/secrets/vault-pass.age`.
2. **Reach the host**: `cd ansible && DEPLOY_HOST=152.228.170.51 uv run --group deploy ansible bot -m ping -b`.
3. **Converge 1.10 first** — today's code, under 3.13 through the new unit, so the mechanism is
   proven without also shipping the hikari port: `DEPLOY_HOST=152.228.170.51 just deploy 1.10`.
   Drops running timers. If the settle check fails, `ansible-playbook timer-bot.yml` from `myserver`
   puts the old unit back.
4. **Verify**: `systemctl status timer-bot` runs `/opt/timer-bot/venv/bin/timer-bot` as `timer-bot`;
   `journalctl -u timer-bot.service` shows the gateway up; `/timer start 0 1` answers in a guild.

## Phase 3 — the agent, once 4 is confirmed

- `myserver`: delete `timer-bot.yml`, `roles/python-worker`, README "Setup the Timer Discord Bot".
- `server-setup/OPERATIONS.md`: drop the `timer-bot.yml` row, the `python-worker` shape section and
  the `/home/lpanhaleux/projects/` paragraph (last `python-worker` gone); `krcg_gra` then has no
  playbook either. Its per-app line says the `ansible/` directories "consume the collection": bots
  don't.
- `server-setup/deploy-targets.yml` provisions `DEPLOY_SSH_KEY` into this public repo's `production`
  environment, and no workflow reads it: ask the human whether CI deploy is wanted, else drop the line.
- Host: remove `/home/lpanhaleux/projects/timer-bot` (human, or with leave).
- `wiki/operations.md`: delete "Until the cutover". `product.md` Status and `CLAUDE.md` "Right now":
  deployed from this repo.
- Delete this file and the board line; egress.

Releasing the hikari port (`just release`, then `just deploy`) is separate and the human's call.
