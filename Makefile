.PHONY: release serve update

release:
	fullrelease

serve:
	source .env && timer-bot

update:
	pip install --upgrade --upgrade-strategy eager -e ".[dev]"
