# 07. Open decisions

Every decision below is Vrushit's. Until it is written in `docs/decisions/`,
the local code treats it as a parameter, a port, or a PROVISIONAL label.

## Decisions with a due date (from CLAUDE.md and the plan)

| Decision | Due | Blocks |
|---|---|---|
| Which AI reads scanned pages | Fri 25 Sep | Sprint 2 development |
| The second, independent reader | Tue 6 Oct | Sprint 3 agreement checks |
| What "verified" promises, in writing | Fri 9 Oct | The labels users see |
| The go or no go bar, as a number | Fri 16 Oct | Launch |

## Sprint 1 design items (issues)

| Item | Issue | Blocks locally |
|---|---|---|
| Database design | #1 | Real repository adapter, record fields |
| Customer separation rule and role | #2, #12 | Real repository adapter, isolation tests at the database |
| Reader contract, including coordinates | #3 | Socket stops being provisional; PDF reader; page box type |
| Local setup and stand-ins | #9 | backend/pyproject.toml, CI backend job, real adapters locally |
| Storage naming rule | #11 | Real storage adapter |

## Questions from the Sprint 1 PRD

Numbers follow the pushed PRD (fork branch `docs/s1-sprint-prd`).

| PRD question | Short form | What the local code assumes (PROPOSAL, not decided) |
|---|---|---|
| 1 | Masking before text is stored | A required masker port with no default; no real rule; made-up files only |
| 2 | Database design | Records and statuses are provisional placeholders |
| 3 | How the server knows the customer | Customer id is an argument to the service |
| 4 | Where the virus scan runs | First step of the worker |
| 5 | Coordinates | Spreadsheet cells only (sheet, row, column) |
| 6 | Scans in Sprint 1 | Marked `needs_reader`, not failed |
| 7 | Endpoints for the screens | Not built |
| 8 | Test database role | Not applicable yet (no database) |
| 9 | Where Day 5 testing runs | Not applicable yet |
| 10 | Tushar's correction flow idea | Originals never overwritten; nothing else built |
| Section 6 | Upload limits, queue settings, libraries | All required parameters, no defaults |

Not yet asked in the PRD, but assumed by the local code: running a job twice
replaces pieces; a queue failure rolls the upload back so a retry works; no
file name is stored.

## A conflict to resolve

On 24 Sep, three design documents were shared ("Day 1 Skeleton PRD",
"Document-to-SQL Pipeline", "Five-Day Laptop Build"). They describe a single
company system with Temporal, SeaweedFS, and an NL-to-SQL agent that writes
SQL for numbers. They also pick the scan AI (Qwen through Ollama or vLLM),
Terraform instead of CDK, and Cognito login, so they touch the decision due
today. Their author and authority are unknown. That conflicts with CLAUDE.md
(several customers separated, numbers only from fixed queries, SQS, S3, CDK). Which design is current is Vrushit's
call; this folder follows CLAUDE.md and the Delivery Plan until he says
otherwise.
