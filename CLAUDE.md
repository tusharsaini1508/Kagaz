# CLAUDE.md

Instructions for Claude Code working in this repository. Read this before touching anything.

## What this product is

Kaagaz is a multi customer SaaS. Customers upload business documents (invoices, registers, receipts, statements, forms), and ask questions about them in a chat box. Every answer must point back to the exact page and the exact spot it came from. If the answer is not in the documents, the system says so rather than inventing one.

Team: Vrushit Patel is the Product Manager and reviews every pull request. Tushar is the engineer. Assume every change you make will be read line by line by a human before it merges.

## Never do these

These are hard rules. If a task seems to require breaking one, stop and ask instead.

1. **Never query the database without the customer filter applied.** Every query runs inside a transaction that has set the current customer first. This is enforced by row level security, but the application code must also be correct. No raw query, migration helper, debug script or test fixture is exempt.
2. **Never add a new dependency without asking.** Not a library, not a tool, not a GitHub Action. Say which one you want and why, and wait. Licence matters as much as function: anything under AGPL or a source available licence is refused outright.
3. **Never let a full Aadhaar or PAN number reach a table, a log line, a trace, an error message, or an AI prompt.** Mask at the moment of capture, before storage and before indexing.
4. **Never commit a secret.** No keys, tokens, passwords, connection strings, or `.env` files. Use environment variables and the secrets store.
5. **Never return a value as fact without page coordinates.** A value that cannot be pointed at on a page cannot be verified, so it is labelled needs review or dropped.
6. **Never guess to fill a gap.** Unreadable is a valid answer for a reader and for the system.
7. **Never push to `master`.** Work on a branch and open a pull request.

## How to work

**Plan first.** Use plan mode before writing code on any task. For anything touching the database schema or customer separation, post the plan in the GitHub issue and wait for approval before starting.

**Small changes.** Target about 300 changed lines per pull request. If the task is bigger, propose a split and do the first part only.

**One job per pull request.** Do not mix a rename or a reformat into a feature change.

**Tests in the same change.** New behaviour gets a test that fails without the change. Bug fixes get a test that reproduces the bug first. Anything touching customer separation gets a test proving one customer cannot reach another customer's data.

**Match the surrounding code.** Same naming, same structure, same comment density as the files around you. Do not introduce a new pattern because you prefer it.

**Do not invent scope.** Build what the ticket asks for. If you spot something else worth fixing, mention it, do not fix it in the same pull request.

## Branches and commits

Branch name: `<type>/<sprint>-<short-name>`, for example `feat/s1-upload-endpoint`.
Types: `feat`, `fix`, `chore`, `docs`, `test`, `infra`.

Pull request title: `feat(s1): upload endpoint with deduplication`.

Fill in the pull request template fully, including acceptance criteria and how you tested.

## Architecture rules that shape the code

- **The reader plug socket.** Anything that reads a document sits behind one interface. Adding or swapping a reader must never require changes outside that interface and its own module. Do not call a reader directly from application code.
- **Every extracted value carries its page and its coordinates.** This is not optional metadata, it is the thing that makes the product sellable.
- **Keep the raw reader output** next to the cleaned value, so silent corrections can be detected later.
- **Numbers come from fixed queries**, not from an AI writing SQL.
- **Customer data never crosses customers.** Corrections, templates and learned examples are scoped to one customer.

## Stack and layout

AWS in Mumbai (ap-south-1). Python with FastAPI for the API. Next.js with PDF.js for the frontend. PostgreSQL with pgvector, full text search and fuzzy matching. S3 for files, one prefix per customer. SQS with worker processes for jobs. AWS CDK for infrastructure.

Folders: `backend/`, `frontend/`, `infra/`, `docs/`. CI looks for `backend/pyproject.toml` and `frontend/package.json` by those exact names.

Open decisions live in `docs/decisions/`. If a decision you need is not recorded there, ask rather than picking one.

## What CI expects from you

CI skips the backend and frontend jobs until those projects exist. Once they do, it runs the following and they must all pass, so set them up on the first day rather than retrofitting later.

Backend, from `backend/`: `ruff check .`, `ruff format --check .`, `mypy .`, `alembic upgrade head` against an empty database, then `pytest`. Every dependency licence is checked and anything AGPL, SSPL or GPL v3 fails the build outright.

**Customer isolation tests carry the pytest marker `isolation`** and run as their own step, before everything else, so a failure is impossible to miss. Any test proving one customer cannot reach another customer's data gets that marker.

Frontend, from `frontend/`: `npm ci`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`.

A red check does not physically block the merge button in this repository, because there is no branch protection. It is still a blocking review comment. Never merge on red.

## When you are unsure

Ask. A question in the issue costs ten minutes. Guessing wrong costs a day, and on a four week schedule that is a real loss.
