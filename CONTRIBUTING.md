# How we work on Kaagaz

Two people, a tight schedule, and an AI assistant that writes code faster than a human can read it. These rules are the brake.

Tushar owns steps marked **T**. Vrushit owns steps marked **V**.

---

## The short version

1. No direct pushes to `master`. Everything goes through a pull request.
2. Every pull request is reviewed by Vrushit before it merges.
3. Keep pull requests small, about 300 changed lines or fewer.
4. Every pull request carries tests.
5. Write the sprint PRD before you write code.

A ruleset on `master` enforces rules 1 to 3: pushes are rejected, a pull request needs Vrushit's approval, and CI has to be green. If a merge is blocked, the reason is written on the pull request. Do not look for a way around it, ask instead.

---

## Where everything lives

| Thing | Where |
|---|---|
| What the sprint delivers, and when | The [delivery plan](https://claude.ai/artifact/Jeebdv68HRvxr8rTMYKe6s) |
| The individual tasks | GitHub **Issues**, grouped by **Milestone**, one per sprint |
| The sprint brief | `docs/prd/sprint-N.md`, from `docs/prd/TEMPLATE.md` |
| Rules for the AI assistant | [CLAUDE.md](CLAUDE.md), loaded automatically every session |
| Decisions already made | `docs/decisions/` |
| Questions and discussion | The issue itself, not chat, so the answer is findable later |

---

# The loop

It repeats every sprint.

## Stage 1. Understand the sprint · T

1. Open the **Milestone** for the sprint in GitHub. It lists every issue with its due date.
2. Filter to issues labelled `owner:tushar`. Those are yours. The `cycle:` label says which part of the sprint each belongs to: design, dev, test, docs or uat.
3. Read the sprint goal and exit gate in the delivery plan.
4. Note the `D1` to `D4` day tags. They are the intended order, not a rule, but the order exists for a reason.

## Stage 2. Write the sprint PRD · T

5. Copy `docs/prd/TEMPLATE.md` to `docs/prd/sprint-N.md`, or run `/sprint-prd` in Claude Code to get a draft.
6. **Rewrite every section in your own words.** The point is not the document, it is finding out what you do not yet understand. A draft you did not rewrite hides exactly the gaps this is meant to expose.
7. Fill the questions section honestly. There is no such thing as too many questions here.
8. Open a pull request with the PRD, or post it on the sprint PRD issue.

## Stage 3. PRD review · V then T

9. Vrushit reads it, answers every question, and either approves the approach or asks for changes.
10. Approval is written into the PRD with a date. A verbal yes does not count, because in three weeks nobody will remember what was agreed.
11. **No code is written before this.** Not a scaffold, not a spike, nothing.

## Stage 4. Pick up a task · T

12. Assign the issue to yourself and take one at a time.
13. Read its acceptance criteria. If they are missing, or you cannot check them yourself, the ticket is not ready: ask in the issue before starting.
14. If the issue is labelled `needs-plan`, meaning it touches the database schema or customer separation, **write your plan as a comment on the issue and wait for Vrushit's approval.** Claude Code's plan mode is the easiest way to produce it.

## Stage 5. Build it · T

15. Branch from `master`:

    ```
    <type>/<sprint>-<short-name>
    ```

    Types: `feat`, `fix`, `chore`, `docs`, `test`, `infra`. Examples:

    ```
    feat/s1-upload-endpoint
    fix/s2-missing-page-image
    infra/s1-cdk-skeleton
    docs/s1-database-diagram
    ```

16. **One job per branch.** A pull request that renames files and adds a feature is two pull requests. If it grows past about 300 changed lines, stop and split it: the plumbing in one, the behaviour in the next. A large pull request does not get reviewed, it gets skimmed, and skimming is how bugs reach `master`.
17. **Tests ship in the same change**, not as a follow up and not as a ticket for later. New behaviour gets a test that fails without the change. A bug fix gets a test that reproduces the bug first.
18. Any test proving one customer cannot reach another customer's data carries the pytest marker `isolation`. CI runs those first and on their own.

## Stage 6. Check it yourself, before Vrushit sees it · T

19. Run the checks locally. From `backend/`: `ruff check .`, `ruff format --check .`, `mypy .`, `pytest`. From `frontend/`: `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`.
20. Run `/pr-check` in Claude Code. It walks the branch against every rule here and reports **READY** or **FIX FIRST**.
21. Fix everything it flags. The point of this stage is that Vrushit's review time goes on judgement rather than on rule breaks.

## Stage 7. Open the pull request · T

22. Open it against `master` and fill the template completely. The acceptance criteria are not optional. If you cannot say what done looks like, the ticket was not ready to start.
23. Put `Closes #<issue>` in the description, so the issue closes itself when the pull request merges.
24. Title it to match the branch: `feat(s1): upload endpoint with deduplication`.
25. Wait for **CI** to go green. A red check blocks the merge.

## Stage 8. Review and merge · V then T

26. Vrushit reviews the same day it opens. If a review has not landed by the end of the day, ping him rather than stacking a second pull request on top of the first.
27. Address the comments and push again. A new push dismisses the previous approval, so it needs approving again.
28. Resolve every conversation. An unresolved one blocks the merge.
29. Vrushit merges, with squash, so `master` stays at one commit per pull request. The branch deletes itself.

## Stage 9. Sprint testing and documentation · T

30. Work the issues labelled `cycle:test`. **Record the actual numbers**, not "it works". How many golden questions were right, how many wrong, and how many correctly answered "not found".
31. Work the issues labelled `cycle:docs`. Documentation is written as the thing is built, not at the end of the project when nobody remembers.

## Stage 10. UAT and sign off · V

32. Vrushit tests the sprint himself against the issues labelled `cycle:uat`.
33. He records **Accepted** or **Rejected** on the delivery plan page, with a date and notes.
34. Anything rejected becomes an issue in the next sprint. Then the loop starts again at stage 1.

---

## The rules that are never bent

Not style preferences. Breaking one is a blocking review comment every time.

- **Never query the database without the customer filter applied.** Every query runs inside a transaction that has set the current customer. No exceptions, not even for a quick script.
- **Never add a new library without Vrushit approving it first**, including its licence. Some licences make a commercial product impossible to ship, and CI fails the build on AGPL, SSPL and GPL v3.
- **Never let a full identity number reach a table, a log file, or an AI prompt.** Aadhaar and PAN numbers are masked at the moment of capture, before anything is stored or indexed.
- **Never commit a secret.** No keys, tokens, passwords, connection strings or `.env` files. If one is committed by accident, tell Vrushit immediately and treat it as compromised.
- **Never show an answer without its source.** A value with no page coordinates cannot be verified, so it cannot be shown as fact.
- **Never game a check.** No deleting or skipping tests, weakened assertions, blanket `try/except`, `# type: ignore`, `eslint-disable`, or `--no-verify`. If a test is wrong, say why and ask.

---

## When you are stuck

| Situation | Do this |
|---|---|
| Acceptance criteria are unclear | Ask in the issue before starting. Do not guess |
| You need a decision only Vrushit can make | Comment on the issue and move to another task. Do not choose for him |
| You want to add a library | Propose it in the issue with its exact name and licence, and wait |
| You noticed something else worth fixing | Say it in one line, open an issue for it, and carry on with your task |
| A hook or permission rule blocked you | Do not work around it. Explain what you needed and ask |
| Three attempts have failed | Stop. Report what you tried, what you learned, and the options |

---

## Decisions

When we choose between real options, write it down in `docs/decisions/` as a short file: what we chose, what we rejected, and why. One page is plenty. Future us will not remember, and neither will the AI assistant.

---

## Questions

Ask early, and ask in the issue rather than in chat, so the answer is findable later. A question that costs ten minutes now is cheaper than a day spent guessing.
