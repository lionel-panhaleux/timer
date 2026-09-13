# Board

What must change. The goal is zero. **Completion is deletion** — no closed state, no archive; git
history is the record. Context lives in [`wiki/`](wiki/index.md), never here: a line that cannot be
completed is documentation, and belongs on a wiki page instead.

**Order is priority**, and priority is decided by these rules, top down:

1. **Blocks someone else** — another person, another repo, another line.
2. **User-visible breakage.**
3. **User-visible feature.**
4. **Internal cleanup.**

Ties break to the smaller line. An item waiting on someone is not a state: it is a dated
follow-up ("chase @someone, 12 Oct"), owned by whoever wrote it.

---

- Refresh the README badges — they claim Python 3.8 and black; it is 3.13 and ruff. Done: badges match `pyproject.toml`.

<!-- cycles-since-upkeep: 4 -->
