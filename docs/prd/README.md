# Sprint PRDs

One PRD per sprint, written by Tushar before any code is written, reviewed by
Vrushit before any code is written.

```
TEMPLATE.md    copy this
sprint-1.md    Foundation
sprint-2.md    The Answer, MVP
sprint-3.md    Trust
sprint-4.md    Launch
```

## Why this exists

Two reasons, and the second one is the real one.

**It is the brief the AI assistant works from.** A vague PRD produces confidently
wrong code, quickly, and at volume.

**It is how we find out whether the sprint is understood before a week is spent
on it.** Writing the plan in your own words exposes the gaps that reading the
issues does not. Every question raised here costs ten minutes. The same question
discovered in review costs a day, and on a four week schedule there are no spare
days.

## How it works

1. Tushar copies `TEMPLATE.md` to `sprint-N.md` and fills it in.
2. He opens a pull request with it, or posts it on the sprint PRD issue.
3. Vrushit reads it, answers every question in section 8, and either approves
   the approach or asks for changes.
4. Only then does development start.

Approval is written into the PRD, at the bottom, with a date. A verbal yes does
not count, because in three weeks nobody will remember what was agreed.
