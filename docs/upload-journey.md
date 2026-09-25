# How the upload journey works

> DRAFT (#31). Describes local, unmerged code on `local/s1-foundation`. Parts
> marked PROVISIONAL wait for Vrushit's decisions.

A customer uploads a file. Here is everything that happens to it, in order,
and what happens when a step fails.

## 1. Upload

The file is read once. While reading, it is fingerprinted (SHA-256), counted,
and copied to a temporary file.

| If | Then |
|---|---|
| It is empty | Refused: `empty_file`. Nothing kept. |
| It is over the size limit | Reading stops one byte past the limit. Refused: `too_large`. Nothing kept. |
| Its first bytes are not a known type (PDF, PNG, JPEG, TIFF, zip, old Office, plain text) | Refused: `unsupported_type`. The file name and what the browser says are never trusted. |
| This customer already uploaded the same bytes | Reply "duplicate" with the existing document. Nothing new stored. Other customers are never checked. |

Otherwise the file is stored under the customer, recorded, and a job is put in
the queue. If storing, recording or queueing fails, the steps already done are
undone so the customer can simply try again.

## 2. Virus scan (first step of the job)

PROVISIONAL: where the scan runs is PRD question 4.

| If | Then |
|---|---|
| The scanner says clean | The document is marked clean. |
| Infected, cannot be scanned, or any unclear answer | Marked rejected for good, the file is quarantined, the job ends: `virus_found` or `unscannable`. |
| The scanner is down | The job is retried later. The file is never opened meanwhile. |

## 3. Read

The exact bytes that were scanned are read through the reader plug socket. They
must still match the upload's fingerprint (`content_changed` otherwise).

| File | Reader | If it fails |
|---|---|---|
| CSV (UTF-8) | CSV reader: every cell with row and column | `not_utf8`, `not_text`, `malformed_csv`, `too_many_cells` |
| Excel .xlsx | Excel reader: every cell with sheet, row and column | `corrupt_file`, `too_large_inside`, `doctype_not_allowed`, `macros_not_allowed`, and others |
| PDF, photos, Word, old Office | None yet | Not a failure: marked `needs_reader` until Sprint 2 or file preparation (#17) |

## 4. Mask, split, save

Every value has full Aadhaar and PAN numbers masked before anything is kept
(PROVISIONAL rule, PRD question 1). The text is split into one piece per row,
and each piece remembers every cell it came from. The document is marked ready.

## When a job keeps failing

A job that fails for a reason a retry could fix is tried again after its lease
runs out. After the maximum number of tries it moves to the failure bin with
its code. A failure a retry cannot fix (a virus, a broken file) goes to the
failure bin at once. One bad file never blocks the files behind it.

## Not built yet

File preparation (#17), page pictures (#18), PDF reading, the upload screen
(#22) and the real storage, database, queue and scanner. See
`backend/README.md`.
