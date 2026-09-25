# Kaagaz backend (local build)

> **LOCAL ONLY.** Written before the Sprint 1 PRD was approved. It must not
> become a pull request until the PRD is approved and each issue's plan is
> agreed (CONTRIBUTING.md stages 3 and 4). Python standard library only.

## What is here

| Folder | Issue | What it does |
|---|---|---|
| `kaagaz/ingestion/` | #14 | Upload: read once (SHA-256, size limit), type from first bytes, per-customer duplicates, store, record, queue, undo on failure |
| `kaagaz/jobs/` | #16 | Worker: one job at a time, retries through leases, failure bin, heartbeat for long jobs |
| `kaagaz/scanning/` | #15 | Virus gate: only an explicit CLEAN goes on; REJECTED is final |
| `kaagaz/reading/` | #19, #21 | Reader plug socket and the CSV reader; every value keeps its sheet, row and column |
| `kaagaz/chunking/` | #20 | One text piece per row, each tracing back to its cells |
| `kaagaz/pipeline.py` | glue | The job handler: record, scan, fingerprint check, read, mask, pieces, status |
| `tests/` | #23, #25, #26 | Tests, in-memory fakes, and the lease queue |

Outside systems (database, file storage, queue, scanner, masker) are small
interfaces ("ports") in the code. Only test fakes implement them today. The
real ones come after Vrushit's designs: #1 and #2 (database), #9 (local
setup), #11 (storage naming), the scanner choice, and the masking rule.

## Run the tests

From this folder (`backend/`):

```
python -X dev -m unittest discover -s tests -t .
python -X dev -m unittest discover -s tests -t . -p "test_isolation_*.py"
```

With pytest installed, `python -m pytest tests` runs the same tests, and
`python -m pytest tests -m isolation` runs the customer isolation tests only
(`tests/conftest.py` adds the marker).

Not set up yet (Vrushit's #9 and #10): `pyproject.toml`, ruff, mypy.

## Rules the code keeps

* Every lookup takes the customer first. Nothing lists across customers.
* No file name is taken, stored or logged. Errors carry short codes only.
* Nothing opens a file before the virus gate says CLEAN.
* Application code reads documents only through `ReaderSocket`
  (a test fails otherwise).
* No limits, retry counts or lease times have defaults: they are settings.
* Anything waiting for a Vrushit decision is marked **PROVISIONAL** in its
  docstring.
