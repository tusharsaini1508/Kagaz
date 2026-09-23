# How we work on Kaagaz

Two people, a tight schedule, and an AI assistant that writes code faster than a human can read it. These rules are the brake.

---

## The short version

1. No direct pushes to `master`. Everything goes through a pull request.
2. Every pull request is reviewed by Vrushit before it merges.
3. Keep pull requests small, about 300 changed lines or fewer.
4. Every pull request carries tests.
5. Write the sprint PRD before you write code.

A ruleset on `master` enforces rules 1 to 3: pushes are rejected, a pull request needs Vrushit's approval, and CI has to be green. If a merge is blocked, the reason is written on the pull request. Do not look for a way around it, ask instead.

---

## Before a sprint starts

Tushar writes a short **sprint PRD**: what is being built this sprint, in his own words. It is the brief his AI assistant works from, and it is the thing Vrushit reviews.

Vrushit then walks through the approach with him and clears any doubts. No code is written until that conversation has happened. Ten minutes here saves a day of building the wrong thing.

---

## Branches

Never commit to `master` directly.

```
<type>/<sprint>-<short-name>
```

Types: `feat`, `fix`, `chore`, `docs`, `test`, `infra`.

Examples:

```
feat/s1-upload-endpoint
fix/s2-missing-page-image
infra/s1-cdk-skeleton
docs/s1-database-diagram
```

Branches are deleted automatically once merged.

---

## Pull requests

**Size.** Aim for about 300 changed lines. A large pull request does not get reviewed, it gets skimmed, and skimming is how bugs reach `master`. If a job is too big, split it: the plumbing in one pull request, the behaviour in the next.

**One job each.** A pull request that renames files and adds a feature is two pull requests.

**Title.** Match the branch, for example `feat(s1): upload endpoint with deduplication`.

**Description.** Fill in the template. The acceptance criteria are not optional. If you cannot say what done looks like, the ticket was not ready to start.

**Review.** Vrushit reviews every pull request the day it opens. If a review has not landed by the end of the day, ping him rather than stacking a second pull request on top of the first.

**Merging.** Squash merge only, so `master` stays at one commit per change. Vrushit merges.

---

## Tests

Every pull request carries its own tests. Not a follow up, not a ticket for later.

What counts:

- New behaviour has a test that fails without the change.
- Anything touching customer separation has a test proving customer A cannot reach customer B's data.
- A bug fix has a test that reproduces the bug first.

---

## Plan before you build

Anything touching the database schema or the customer separation gets a written plan approved before a line of code. Post the plan in the issue, wait for a thumbs up, then start.

If you use Claude Code, run plan mode first on every task and paste the plan into the issue.

---

## The rules that are never bent

These are not style preferences. Breaking one is a blocking review comment every time.

- **Never query the database without the customer filter applied.** Every query runs inside a transaction that has set the current customer. No exceptions, not even for a quick script.
- **Never add a new library without Vrushit approving it first**, including its licence. Some licences make a commercial product impossible to ship.
- **Never let a full identity number reach a table, a log file, or an AI prompt.** Aadhaar and PAN numbers are masked at the moment of capture, before anything is stored or indexed.
- **Never commit a secret.** No keys, tokens, passwords, connection strings or `.env` files. If one is committed by accident, tell Vrushit immediately and treat it as compromised.
- **Never show an answer without its source.** A value with no page coordinates cannot be verified, so it cannot be shown as fact.

---

## Decisions

When we choose between real options, write it down in `docs/decisions/` as a short file: what we chose, what we rejected, and why. One page is plenty. Future us will not remember, and neither will the AI assistant.

---

## Questions

Ask early, and ask in the issue rather than in chat, so the answer is findable later. A question that costs ten minutes now is cheaper than a day spent guessing.
