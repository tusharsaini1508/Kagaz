# Sprint N PRD: <sprint name>

**Written by:** Tushar
**Date:**
**Sprint dates:**
**Reviewed by Vrushit on:**
**Status:** Draft | Approved

> Copy this file to `docs/prd/sprint-N.md` and fill it in **before** you write any
> code. Write it in your own words, not by copying the issue titles. The point is
> to find out whether the sprint is actually understood, and to surface your
> questions while they are still cheap to answer.
>
> This is also the brief your AI assistant works from, so vagueness here becomes
> wrong code later.

---

## 1. What this sprint delivers

In three or four sentences, in plain English, what will exist at the end of this
sprint that does not exist now? Write it so someone non technical could read it.

## 2. What this sprint deliberately does not deliver

Just as important. List the things a reader might reasonably assume are included
but are not, and say which sprint they land in instead.

- Not in this sprint:
- Not in this sprint:

## 3. How I will know it is done

The sprint's exit gate, in your words. One or two sentences. If you cannot write
this, you do not yet understand the sprint.

---

## 4. The work, in the order I plan to do it

List the issues you will pick up, in the sequence you intend to build them, and
say why that order. Ordering is a real decision: it decides what is blocked by
what, and where you get stuck.

| # | Issue | What it is | Why it comes here |
|---|---|---|---|
| 1 | #  |  |  |
| 2 | #  |  |  |
| 3 | #  |  |  |

**Roughly how long:** your own estimate per issue, in half days. Being wrong is
fine and expected. Not estimating means nobody notices you are behind until the
last day.

---

## 5. How I intend to build the tricky parts

Pick the two or three items above that are not obvious, and describe your
approach in a short paragraph each. Not code, just the shape of it: which
components, what talks to what, what gets stored where.

This is the section Vrushit will push back on hardest, and that is the point.
Being corrected here costs ten minutes. Being corrected in review costs a day.

**<issue title>**

**<issue title>**

---

## 6. Decisions I am making myself

Choices you are taking without asking, and the reason. Library choices, file
layout, naming, data shapes. If Vrushit disagrees with one, he will say so here
rather than in review.

Anything touching the database schema, customer separation, or a new dependency
does **not** belong in this list. Those need approval, so put them in section 7.

-
-

## 7. Things I need approved before I start

Anything from CLAUDE.md that requires a decision from Vrushit: schema changes,
customer separation, new dependencies including their licences.

| What | Why I need it | Approved |
|---|---|---|
|  |  | [ ] |
|  |  | [ ] |

## 8. Questions

Everything you are unsure about. There is no such thing as too many here, and a
question you did not ask becomes a day of rework.

1.
2.
3.

## 9. What could make this slip

The parts you are least confident about, and what you would drop first if the
sprint runs long. Say it now, while it is a plan rather than an excuse.

-
-

---

## 10. Before I start, I confirm

- [ ] I have read CLAUDE.md and CONTRIBUTING.md in this sprint, not just once months ago
- [ ] Every issue I listed has acceptance criteria, and I understand each one
- [ ] I know which of my tasks touch the database or customer separation
- [ ] I know what CI will check, and I can run those checks locally before opening a pull request

---

## Vrushit's review

**Approach:** Approved | Changes needed
**Answers to the questions above:**
**Changes I want to the plan:**
**Anything I am adding or removing from the sprint:**

**Approved on:**
