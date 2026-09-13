default:
    @just --list

# Install / refresh dev dependencies
update:
    uv sync --upgrade --group dev

# Lint
lint:
    uv run ruff check
    uv run ruff format --check

# Format
fmt:
    uv run ruff check --fix
    uv run ruff format

# Type check
typecheck:
    uv run ty check --error-on-warning

# Run tests
test:
    uv run pytest

# Run the bot locally (sources .env)
serve:
    set -a && source .env && set +a && uv run timer-bot

# Deploy a PyPI release to gravelines (defaults to the version in pyproject.toml). Needs DEPLOY_HOST.
deploy version="":
    #!/usr/bin/env bash
    set -euo pipefail
    : "${DEPLOY_HOST:?set DEPLOY_HOST to the bot host address}"
    [[ -f ansible/.vault_pass ]] || { echo "no ansible/.vault_pass — age -d -i ~/.ssh/<key> -o ansible/.vault_pass ansible/secrets/vault-pass.age"; exit 1; }
    version="{{ version }}"
    [[ -n "$version" ]] || version=$(uv version --short)
    cd ansible
    uv run --group deploy ansible-playbook deploy.yml -e version="$version"

# Remove build artifacts
clean:
    rm -rf dist build *.egg-info src/*.egg-info

# Bump version, tag, build, push, publish to PyPI. Working tree must be clean.
# Default bump is minor (project versioning is major.minor only); pass `just release major` for a major bump.
release bump="minor":
    #!/usr/bin/env bash
    set -euo pipefail
    git diff --exit-code --quiet
    new=$(uv version --bump {{ bump }} --short)
    git add pyproject.toml uv.lock
    git commit -m "release: v$new"
    git tag "v$new"
    rm -rf dist
    uv build
    git push origin HEAD
    git push origin "v$new"
    uv publish
