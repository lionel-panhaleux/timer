#!/bin/sh
# SessionStart: show the live board. CLAUDE.md carries the rules; only this can carry the state.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
[ -f BOARD.md ] || exit 0
printf '## The board right now\n\n'
sed -n '/^---$/,$p' BOARD.md | sed '1d'
printf '\nRead wiki/index.md before changing anything. /intake to add a line, /ship to take the top one.\n'
exit 0
