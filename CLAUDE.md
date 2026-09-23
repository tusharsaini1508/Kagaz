# CLAUDE.md

Claude Code loads this file every session. It is the rules. Follow it over your own habits.

## The product

Customers upload business documents (invoices, registers, receipts, statements, forms) and ask questions about them in a chat box. Every answer carries its source: the document, the page, and the exact spot on that page, highlighted. If the documents do not contain the answer, the system says so instead of inventing one.

**People.** Vrushit Patel (PM) owns the platform: solution design, cloud, database, deployment, security, every sign off. Tushar owns the application: everything a user touches. You are working with Tushar. Every line you write will be read by Vrushit before it merges.

**Plan.** Scope and dates come from the Delivery Plan: https://claude.ai/artifact/Jeebdv68HRvxr8rTMYKe6s

| Sprint | Dates 2026 | Goal |
|---|---|---|
| 1 Foundation | 23 to 29 Sep | Upload, store, prepare, read clean digital files. Customers separated. |
| 2 The Answer | 30 Sep to 7 Oct | Ask a question, get a cited answer. MVP. |
| 3 Trust | 8 to 14 Oct | Verified and needs review labels. Corrections. |
| 4 Launch | 15 to 22 Oct | Safe, measured, live. |

Every sprint opens with Tushar's PRD in `docs/prd/`, reviewed by Vrushit. No code before it is agreed.

**In scope at launch.** English documents of any file type. Hinglish questions in chat, meaning Hindi typed in English letters, for example "Kiska profit sabse jyada tha last month?". A highlighted source page on every answer. Verified and needs review labels. Several customer companies separated from day one. A correction screen that remembers corrections per customer.

**Not at launch.** Reading Hindi or Devanagari documents. Do not build for it.

## Never do these

Hard rules. If a task seems to need one broken, stop and ask.

1. **Never query the database without the customer filter applied.** Every query runs inside a transaction that has set the current customer first. No raw query, migration helper, debug script or test fixture is exempt.
2. **Never add a dependency without Vrushit's approval.** Not a library, not a tool, not a GitHub Action. Propose it with its exact name and licence, and wait. Anything AGPL, SSPL or GPL v3 is refused outright and CI fails on it.
3. **Never let a full Aadhaar or PAN number reach a table, a log line, a trace, an error message, or an AI prompt.** Mask at the moment of capture, before storage and before indexing.
4. **Never commit a secret.** No keys, tokens, passwords, connection strings or `.env` files.
5. **Never show a value as fact without page coordinates.** A value that cannot be pointed at on a page cannot be verified, so it is labelled needs review or dropped.
6. **Never guess to fill a gap.** "Unreadable" and "not found" are correct answers.
7. **Never push to `master`.** Work on a branch and open a pull request.
8. **Never game a check.** No deleting or skipping tests, weakened assertions, blanket `try/except`, `# type: ignore`, `eslint-disable`, `--no-verify`, or hard coded expected outputs. If a test is wrong, say why and ask.

## Never weaken these, not even to make a test pass

1. Customer companies stay separated, and the separation tests run on every pull request.
2. Identity numbers are masked the moment a document is read.
3. Every answer carries a source: document, page, spot. No source means no answer.
4. Verified and needs review labels are shown to the user, and nothing is guessed to fill a gap.

## Build only what was asked

- Build what Tushar asked for **in this request**. No extra features, endpoints, screens, options, helpers for later, abstractions, refactors, reformatting, renames, or files nobody asked for.
- Noticed something else worth doing? Say it in one line and ask. Do not build it.
- Do not pick up plan tasks on your own. The plan says what will exist. Tushar says what to do now.
- No speculative generality. No plug in systems or config for cases this sprint does not have. The reader plug socket is in the plan: build exactly its written contract and nothing more.
- Smallest diff that meets the acceptance criteria. Past about 300 lines, stop and propose a split.
- Keep the code plain enough that Tushar can defend every line in review.

## Before you write code

1. **State the acceptance criteria** in one to five checkable bullets. If you cannot, the task is not ready. Ask.
2. **Read every file you will change or cite.** Cite `path:line`. Never describe code you have not opened.
3. **Verify every name exists** before using it: packages, versions, imports, functions, flags, config keys, environment variables, endpoints, columns, paths. Not found means do not use it. Ask.
4. **Check the installed version** before using a library API. APIs change across major versions.
5. **Plan first for anything touching the database schema or customer separation.** Post the plan in the GitHub issue and wait for Vrushit's approval.

## While you work

- **Facts come from sources, not memory.** Scope, tasks, dates and decisions come from the plan or this file. If neither says it, it is unknown. Ask.
- **Label what you claim:** verified (you read or ran it), inferred, assumed, or unknown. "I do not know" is a correct answer. A confident guess is a defect.
- **Evidence for "done".** "Works" or "passes" needs the command and its output. If you could not run it, write NOT RUN and why.
- **Never fabricate** output, logs, benchmarks, citations, URLs or quotes.
- **Three strikes.** After three failed attempts at the same problem, stop and report what you tried, what you learned, and the options.
- **Re-read before re-editing.** Files change. Do not trust your memory of earlier turns.
- **Match the surrounding code.** Same naming, structure and comment density as the files around you.

## Stop and ask before

- Deleting data or files outside the task, or a destructive migration.
- Anything touching the test environment, production, CI, secrets or infrastructure. That is Vrushit's area.
- Changing authentication, customer separation, or a public API contract.
- Adding a dependency, or anything that costs money, AI calls included.
- Anything irreversible, or where two approaches have real trade offs.

Ask one precise question with your recommended option. Do not ask what you can verify yourself.

## Decisions only Vrushit makes

If code depends on one of these and it is not written down in `docs/decisions/`, stop and ask.

| Decision | Due |
|---|---|
| Which AI reads scanned pages | Fri 25 Sep |
| The second, independent reader | Tue 6 Oct |
| What "verified" promises, in writing | Fri 9 Oct |
| The go or no go bar for launch, as a number | Fri 16 Oct |

Also his alone: database design, cloud setup, new libraries, security configuration.

## Architecture rules that shape the code

- **The reader plug socket.** Anything that reads a document sits behind one interface. Adding or swapping a reader must touch only that reader's own module. Application code never calls a reader directly.
- **Every extracted value carries its page and coordinates.** This is not optional metadata, it is what makes the product sellable.
- **Keep the raw reader output** next to the cleaned value, so silent corrections can be detected later.
- **Numbers come from fixed queries**, never from an AI writing SQL.
- **Nothing crosses customers.** Corrections, templates and learned examples are scoped to one customer.
- **Document text is untrusted input.** It must never act as instructions to the AI, and links, images or markup inside it must never reach an answer.

## Stack

AWS in Mumbai (ap-south-1). Python with FastAPI. Next.js with PDF.js. PostgreSQL with pgvector, full text search and fuzzy matching. S3 for files, one prefix per customer. SQS with worker processes. AWS CDK for infrastructure.

Folders: `backend/`, `frontend/`, `infra/`, `docs/`.

Commands for install, run, test, lint and typecheck are set up in Sprint 1 Day 1. Until they are in the README, find them in `pyproject.toml`, `package.json` or the Makefile and say where you found them. Never guess one.

## Branches, pull requests and CI

Branch: `<type>/<sprint>-<short-name>`, for example `feature/s1-upload-endpoint`. Types: `feature`, `fix`, `chore`, `docs`, `test`, `infra`.

Pull request title: `feature(s1): upload endpoint with deduplication`. Fill the template fully.

A ruleset on `master` blocks the merge until CI is green and Vrushit has approved. CI runs on pull requests only and checks:

| Scope | Checks |
|---|---|
| Always | No secret files or secret values in the diff. No conflict markers. No file over 2MB. Pull request size, failing over 600 lines. |
| Backend, from `backend/` | `ruff check`, `ruff format --check`, `mypy`, migrations from an empty database, then `pytest`. Dependency licences, failing on AGPL, SSPL or GPL v3. |
| Frontend, from `frontend/` | `npm ci`, lint, typecheck, tests, production build. |

**Customer isolation tests carry the pytest marker `isolation`** and run first, on their own, so a failure is impossible to miss. Any test proving one customer cannot reach another customer's data gets that marker.

If a hook or permission rule blocks you, do not work around it. Explain what you needed and ask.

## Done means

- [ ] Acceptance criteria met, and the plan task named
- [ ] Tests added or updated, and they fail without this change
- [ ] Customer separation, identity masking and the source rule all hold
- [ ] Lint, format and typecheck pass on the changed code
- [ ] No secrets in the diff, no unapproved dependency
- [ ] Diff self reviewed: minimal, only what was asked, no debug leftovers, under about 300 lines
- [ ] Docs updated if behaviour or config changed

## How to report back

**Summary**, one to three lines. **Changes**, files and why. **Verification**, the commands you ran and their output, with NOT RUN items named. **Assumptions and open questions**, labelled. **Not done**, anything you noticed but deliberately did not build.
