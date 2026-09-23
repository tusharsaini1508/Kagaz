---
name: pr-check
description: Check the current branch against this repository's pull request rules before Tushar opens a PR for Vrushit's review. Covers size, one job per PR, acceptance criteria, tests, the customer filter, identity numbers, unapproved libraries, scope creep and secrets. Use when Tushar says pr check, ready for PR, can I raise the PR, or before any pull request is opened. Reports READY or FIX FIRST.
---

# PR check

A fast, evidence based gate, so Vrushit's review time goes on judgement rather
than on rule breaks.

**Report only.** Do not fix anything unless Tushar asks. Never commit, never
push, never open the pull request.

## 1. Scope the diff

- Run `git status`, `git diff --stat master...HEAD`, and the full
  `git diff master...HEAD`.
- Get two things from Tushar, the pull request draft, or the commit messages:
  **what was asked**, and **which issue it closes**.

## 2. Run the checks

| # | Check | How | Fails when |
|---|---|---|---|
| 1 | Size | added plus removed lines from `--stat`, counting lock files separately | over about 300 lines of hand written code |
| 2 | One job | read the diff against the stated task | the changes serve more than one purpose |
| 3 | Scope | every changed hunk maps to what was asked | extra features, refactors, reformatting, or files nobody asked for |
| 4 | Acceptance criteria | stated in the issue or the pull request description | missing, or not checkable by someone else |
| 5 | Tests ship with it | new or changed tests in the diff cover the criteria | behaviour changed with no test |
| 6 | Tests pass | run the project's test command and show the output | fails, or NOT RUN with no reason |
| 7 | Lint, format, types | `ruff check`, `ruff format --check`, `mypy` in `backend/`; lint, typecheck and build in `frontend/` | errors in the changed files |
| 8 | Customer filter | every new or changed query, ORM call, storage path, search call and cache key | any one of them without the customer filter applied |
| 9 | Isolation test | touches data, so a test proves customer A cannot reach customer B | missing, or missing the `isolation` marker |
| 10 | Identity numbers | read the diff for anything that logs, stores or prompts raw document text or extracted fields | a full Aadhaar or PAN could reach a table, a log or an AI prompt |
| 11 | Source on answers | touches answering, so no path can return an answer without document, page and spot | a sourceless path exists |
| 12 | New libraries | diff of `pyproject.toml`, `requirements*.txt`, `package.json` and lock files | any addition without Vrushit's approval recorded, including its licence |
| 13 | Secrets and leftovers | search for keys, tokens, `.env` values, `print`, `console.log`, `debugger`, `.only`, commented out code, TODOs with no issue | any found |
| 14 | Gaming a check | skipped or deleted tests, weakened assertions, `# type: ignore`, `@ts-ignore`, `eslint-disable`, blanket `try/except` | any found |

Skip rows that do not apply and say why, for example "8 and 9 not applicable,
no data access in this diff". If a command does not exist yet, write
`NOT RUN, no <x> command configured`.

**Never mark a row as passed without evidence:** a command and its output, or a
`path:line`.

## 3. Report

```
PR CHECK   <branch> into master        Closes #<issue>

| # | Check | Result | Evidence |

BLOCKERS:
WARNINGS:
VERDICT: READY | FIX FIRST
```

## 4. If READY

Draft the pull request description by filling in
`.github/pull_request_template.md`: what changed and why, the issue it closes,
the acceptance criteria, how it was tested with commands and their output, and
what Vrushit should look at closely, such as separation, masking or migrations.

Hand the text to Tushar. He opens the pull request.
