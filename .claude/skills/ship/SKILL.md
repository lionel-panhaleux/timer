---
name: ship
description: Execute a board line end to end — pick it, do the work, land the trinity (code + wiki + board line deleted), then spawn the egress reviewer. Use to start or continue work on anything tracked in BOARD.md, and as the default way substantive changes land in this repo.
---

# /ship — execute one line

Arguments, if any, name the line. Otherwise take the **top** line of `BOARD.md`.

## 1. Claim

Read `BOARD.md` and `wiki/index.md`. If another agent is working `master`, note which line it claimed
and stay off its files where you can. Announce the line you are taking.

If the line names a `board/<slug>.md`, read it: it holds the elaborated contract — scope, hazards,
plan — and it is where any working notes belong for the duration.

## 2. Do the work

Read the wiki pages the line touches before the code — `wiki/discord.md` for anything that talks to
Discord. Fan out explorer subagents freely — reading is cheap, and the board is what must stay short,
not the investigation. Implementation runs on Sonnet by default.

**Scope grows in place.** When exploration reveals adjacent necessary work that shares the
abstraction, do it inside this task. Only genuinely separable discoveries go back through `/intake`.
Never leave the board longer than you found it, minus the line you completed.

Hold to `wiki/dogmas.md` while you write: tight and local, no TODOs, comments only for traps, no
mocks of our own code, tests at the boundary.

Pushing, `just release` and any deploy are outward-facing: stop and ask before each.

## 3. Land the trinity

One unit of work is **one landing**, all three parts together:

1. **Code** changed and green — `just lint` and `just test`.
2. **Wiki** — every page named in the line's doc-impact updated, or the absence justified in a
   sentence. A pivot is an edit: the wiki never keeps a deprecated fact, git keeps the history. If
   the work changed a standing decision, the decision line changes here, with one line of rationale
   only when the rejected alternative is attractive enough that someone would plausibly redo it.
   Keep the `Status` section of `wiki/product.md` true.
3. **Board** — delete the line. Delete its `board/<slug>.md` too, unless another line still points at
   it. Completion is deletion; there is no done section.

Then commit to `master` (trunk-based, no feature branch). Describe the change itself; `Fixes #N` only
for a real GitHub issue.

## 4. Egress

Spawn the `egress-reviewer` subagent. It has not seen this conversation, and must not: give it the
commit range or diff, the board line text you just deleted, and nothing else — it reads `wiki/` and
the code itself.

- **Blocking** findings: fix them in this task and re-run the reviewer. Expect first-round scope
  growth — the reviewer may require the refactoring or deletion *now* rather than as a follow-up
  line, and that is its job.
- **Advisory** findings: record them in your report to the human. `/upkeep` mines them; three
  occurrences of the same class is a harness problem, not a code problem.
- After **two** rejection rounds, stop and escalate the disagreement to the human, compressed to its
  inflexion point. Do not go to three.

"Looks good" is a valid and common verdict.

## 5. Report

Tell the human: the line, what landed, which wiki pages moved, the commit, and any advisory findings.
Then bump the counter in `BOARD.md` — `<!-- cycles-since-upkeep: N -->` — by one. At 20, or a month
after the last `/upkeep`, run `/upkeep`.
