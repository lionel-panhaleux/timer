---
name: upkeep
description: The maintenance loop — guard against rot across the wiki, the board and the harness itself. Run every 20 shipped lines (the counter at the bottom of BOARD.md) or monthly, whichever comes first, and whenever the wiki feels out of step with the code.
---

# /upkeep — guard against rot

Three surfaces, in this order. Anything untouched for 20 cycles goes on trial. Lint sweeps run on
Haiku subagents; bring judgement to the verdicts.

## 1. Wiki lint

Fan out Haiku readers over `wiki/`, one page each, plus the code each page claims to describe. Report:

- **Contradictions** between pages.
- **Stale claims** — a page says something the code no longer does. Check the specifics: named
  functions, constants (`THRESHOLDS`, `DISPLAY_SECONDS`, `PAUSE_TIMEOUT`), commands and options, env
  vars, `just` recipes, deploy paths.
- **Orphans** — a page unreachable from `index.md`, or reachable but cited by nothing and touched by
  nothing in 20 cycles. Eviction candidate.
- **Overgrown pages** — `product.md` and `dogmas.md` are meant to become broad summaries that defer
  depth to topic pages. A topic page earns existence only when the summary line pointing at it is
  much shorter than what it holds; if it isn't, fold it back.
- **Domain claims have no code to lint against.** Check their *sources* instead — re-fetch the
  Discord references and the hikari source cited on `discord.md`, and check the locked `hikari`
  version still matches what the page describes. An interview-sourced fact
  carries a date — flag anything over a year old for re-interview.

Fix what is unambiguous in place. Anything needing a decision goes through `/intake`.

## 2. Board eviction

Walk `BOARD.md` **oldest-first** — `git blame BOARD.md` knows line age. Every line gets a verdict, no
line skipped twice running:

- **do** — it is still right and it is next; move it up.
- **date** — it is a follow-up, not a task; rewrite it as one with a date.
- **promote** — it has no done-condition and never did; move the content to a wiki page, delete the
  line.
- **drop** — it stopped mattering. Delete it. **A drop that was a promise to a person (a GitHub issue
  reporter) is something to say, not just delete.**

The human owns drops and reordering. Then ask the frame questions: are the ranking rules still true?
Is the board trending shorter? What should resurface? Open GitHub issues
(`gh issue list --repo lionel-panhaleux/timer`) are a feed: each either has a line or has an answer.

## 3. Harness ratchet

Mine the last 20 cycles — `egress-reviewer` findings (each `/ship` report lists them and what was
done), findings contested as wrong, and corrections the human made by hand.

**Three occurrences of the same class is a harness problem, not a code problem.** Propose the
amendment that would have prevented all three: a line in `wiki/dogmas.md`, a clause in the reviewer's
charter, a lint rule, an edit to one of these skills, a hook. Put it through `/intake` like any other
work.

Then reset the counter: `<!-- cycles-since-upkeep: 0 -->` at the bottom of `BOARD.md`.
