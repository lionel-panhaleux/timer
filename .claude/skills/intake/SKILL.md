---
name: intake
description: The ingress loop — challenge an incoming request, idea or discovery before it reaches BOARD.md. Use whenever new work arrives (a user ask, a GitHub issue, something found mid-task) and it is not going to be done right now. Also use when tempted to write a TODO, a plan document or a follow-up ticket.
---

# /intake — guard coherence

No work reaches the board unchallenged. Ingress **proposes**; the human accepts. Refusing a line is
far cheaper than evicting one later. This is judgement work: run it on the strongest model.

Read `wiki/index.md` and `BOARD.md` first. Then, for each incoming item, answer four questions out
loud, briefly:

## 1. Conflict

Does it contradict a decision in `wiki/dogmas.md`, a scope line in `wiki/product.md`, or a Discord
constraint in `wiki/discord.md`? Does it duplicate a line already on the board?

- Contradicts a decision → **surface it as a decision to overturn**, not as a task. Changing a
  decision is valid work; silently violating one is not. Say which page and which line.
- Duplicates a line → say so and stop. Sharpen the existing line if the new information improves it.

## 2. Completability

Can you state a done-condition, machine-verifiable where possible ("`just test` green with a test
starting two timers in one channel", "`grep -c TODO` is 0", "`systemctl is-active timer-bot`")?

- No done-condition → **it is not a line, it is documentation.** Put it on the right wiki page and
  say which. "Keep an eye on X" is always this.
- Waiting on a person is not a state — write it as a dated follow-up ("chase @someone, 12 Oct").

## 3. Scope

Split **only on real abstraction boundaries**, so an agent can hold each part in context. Never split
to defer, and never split into a hierarchy — a hierarchy is a plan, and plans are pages.

If the item is small enough to do now and nothing is in flight, the right answer is often "do it
now", not "add a line".

## 4. Doc-impact

Name the `wiki/` pages the work will change, or state "none" with a reason. Egress checks this. An
item whose doc-impact is "a new page" is usually a decision to make first.

## Then

Propose the line to the human — the exact text, and where it sits in the order per the ranking rules
at the top of `BOARD.md`. On acceptance, insert it at that position: one line, however long, carrying
the ask, its done-condition and its doc-impact.

Bulky context for an in-flight line goes in `board/<slug>.md` and is deleted with the line. Do not
create one for a line you are not about to ship.
