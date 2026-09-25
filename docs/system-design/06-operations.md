# 06. Operations

Cloud setup, deployment and security configuration are Vrushit's. This page
lists what the plan already says, and marks the rest **PROPOSAL**.

## Deployment (from the plan)

```mermaid
flowchart LR
    dev["Tushar's machine<br/>(Sprint 1: local run, #9)"] -->|pull request| ci["GitHub CI<br/>guardrails, then lint, format, types,<br/>migrations, isolation tests, all tests, build<br/>(backend job skips until backend/pyproject.toml exists)"]
    ci -->|Vrushit approves, squash merge| master["master"]
    master -->|auto deploy (#13)| test["Test environment<br/>AWS Mumbai"]
    test -->|go or no go, 22 Oct| prod["Production<br/>AWS Mumbai"]
```

* Infrastructure is code (AWS CDK), nothing clicked together by hand (#11).
* Nothing in the account is publicly reachable (#11). How customers reach the
  app is OPEN.
* A deployment can be rolled back (#13).

## Scaling (PROPOSAL)

| Part | Scales by | Notes |
|---|---|---|
| API | More instances behind a load balancer | Stateless; uploads spool to disk above a threshold |
| Workers | More worker processes reading the same queue | Each job is independent; leases stop double work |
| Database | Bigger instance first; read replica for search later | Indexes on (customer, fingerprint), (customer, document) |
| Storage | S3 scales on its own | One prefix per customer |
| AI calls | Router sends only scans and hard pages to the expensive reader (Sprint 2) | Spending caps and alerts before the first call (plan S2 D1) |

Measured numbers come from #24 (fifty files, timings) and Sprint 4 testing
(one thousand pages at once).

## Observability (plan Sprint 3 D3 and Sprint 4 D1)

* A tracking dashboard: open any document or question and see what happened.
* Logs carry ids and codes only: customer id, document id, size, type, error
  code, attempt. Never file content, file names or cell values.
* Alerts on every part, with a real person woken when it matters.
* The failure bin (dead letter queue) is watched, not left to fill silently.

## Cost (plan Sprint 2 testing)

Cost per document and cost per question are recorded from week two. Usage is
counted per customer (Sprint 4).

## Backups (plan Sprint 4 D2)

Backups run, and a restore is tested into a clean environment, not assumed.
