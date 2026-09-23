---
name: sprint-prd
description: Draft the sprint PRD that opens Day 1 of every sprint, the brief Vrushit reviews before any code starts. Use when Tushar asks for the sprint PRD, the Day 1 brief, or what he is building this sprint. Takes an optional sprint number and otherwise uses the sprint containing today's date.
---

# Sprint PRD

Day 1 of every sprint opens with this document, not with code. It is the brief
Tushar's assistant works from and what he will defend in Vrushit's review.

**This skill writes one document and no code.** Your job is to produce a draft
good enough for Tushar to argue with, not a finished document.

## 1. Read the template first

Open `docs/prd/TEMPLATE.md` and follow its sections exactly, in its order.
Do not work from a remembered version of it: Vrushit edits it, and the file on
disk is the current one.

## 2. Get the sprint from the plan, never from memory

| Sprint | Dates 2026 |
|---|---|
| 1 Foundation | 23 to 29 Sep |
| 2 The Answer, MVP | 30 Sep to 7 Oct |
| 3 Trust | 8 to 14 Oct |
| 4 Launch | 15 to 22 Oct |

Take the sprint from the argument, or from today's date.

Then gather the real tasks:

1. **GitHub issues are the source of truth.** List the open issues on that
   sprint's milestone. Each one carries its owner label, its planned day, and
   its acceptance criteria. Use them.
2. **The delivery plan** at the URL in CLAUDE.md gives the sprint goal and the
   exit gate. Read it with the Artifact tool if you can reach it.
3. **The repository as it stands.** Read what already exists, so the draft plans
   the work that is actually left rather than work already done.

If you cannot reach the plan or the issues, ask Tushar to paste them.
**Never reconstruct tasks from memory.**

## 3. Write `docs/prd/sprint-<N>.md`

Copy the template and fill every section. While drafting:

- **Add nothing the issues and the plan do not have.** If you think something is
  missing, it goes in the questions section as a question, not into the plan.
- **Choose nothing that is Vrushit's to choose.** No stack, library, schema or
  AI reader. If a task depends on an undecided one, that is a question.
- **Separate the two approval lists carefully.** Ordinary choices Tushar is
  making himself go in one section. Anything touching the database schema,
  customer separation, or a new dependency goes in the section that needs
  Vrushit's sign off before work starts.
- **Every task gets checkable acceptance criteria**, taken from its issue where
  the issue has them.
- **Plain English, short sentences, no polish.** Tushar rewrites this in his own
  voice before the review, and a polished draft discourages him from doing that.

## 4. Hand over

Tell Tushar three things:

1. The file path.
2. The three to five questions most worth raising with Vrushit, and why each one
   matters.
3. That he must rewrite the sections in his own words before the review.

Then stop. No code until he says the PRD is agreed.
