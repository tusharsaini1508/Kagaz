# Sprint 1 PRD: Foundation

**Written by:** Tushar, with Claude Code
**Date:** 23 Sep 2026
**Sprint dates:** Wed 23 Sep to Tue 29 Sep 2026, 5 working days
**Reviewed by Vrushit on:**
**Status:** Draft, ready for review

> My answers, written up in simple English with Claude Code. Based on the delivery
> plan and issues #1 to #36. Words that may be new are explained at the end, in
> "Words used here".

---

## 1. What this sprint delivers

A user uploads a file. We check it for viruses. We save a picture of every page.
For normal PDF, Excel and CSV files, we take the text out, and each piece of text
remembers where on the page it came from. Each customer's files stay separate from
every other customer. No AI and no chat yet.

The journey of one file:

```text
Upload -> Virus check -> Keep one copy -> Prepare the file -> Picture of every page
       -> Take the text out -> Save the text in pieces, each with its page and position
```

**Why the position matters.** In Sprint 2 every answer must show the exact spot on
the page. If the position I save now is wrong, the highlight will be wrong later.

## 2. What this sprint deliberately does not deliver

| Not in Sprint 1 | When |
|---|---|
| Reading scanned pages and photos with AI. This sprint only marks the pages that need a reader. | Sprint 2, after Vrushit picks the reader (due Fri 25 Sep) |
| Hiding Aadhaar and PAN numbers. This sprint already saves text, see question 1. | Sprint 2 in the plan. I suggest earlier. |
| Search and chat, including meaning search with pgvector | Sprint 2 |
| Verified and needs review labels, the second reader, fixing wrong words | Sprint 3 |
| My idea for the review and correction flow, see question 10 | Not in the plan yet |
| Login, see question 3 | Not in any sprint of the plan |
| Cloud (#11), the database itself (#12) and deployment (#13) | Vrushit builds these this sprint. I work on my own machine. |
| Hindi or Devanagari documents | Never at launch |

## 3. How I will know it is done

- I upload fifty different files, and they are all saved with a picture of every page. Every failure is explained (#24).
- The test that proves customer A cannot see customer B's files passes on every pull request (#23).
- Vrushit tests it himself on Day 5, and it passes (#33 to #36).

---

## 4. The work, in the order I plan to do it

First I build upload, because nothing works without a file. Then the virus check,
because nothing may open a file before it is checked. Then the steps that work on
the file, in the order the file goes through them.

**DB** means the task touches the database, so I post a plan on the issue and wait
for Vrushit's OK before I write code.

| # | Issue | What | Needs first |
|---|---|---|---|
| 1 | #6 | This PRD | Nothing |
| 2 | #14 | Upload: fingerprint the file, skip duplicates, save it in the customer's own space, put it in line for processing. DB | Database design (#1, #2), local setup (#9), question 3 |
| 3 | #23 | Test that customer A cannot see customer B. DB | The database (#12), upload (#14) |
| 4 | #15 | Virus check before anything opens a file. DB | Scanner library, upload (#14), question 4 |
| 5 | #16 | Worker that processes files, with retries and a failure bin. DB | Local setup (#9), the database (#12) |
| 6 | #22a | Upload screen and file list with status | Upload (#14), worker (#16) |
| 7 | #17 | Prepare the file: Office to PDF, phone photos, straighten scans | Libraries |
| 8 | #18 | Save a picture of every page. DB | Rendering library, the database (#12) |
| 9 | #19 | Take text out of PDF, Excel and CSV. DB | Libraries, reader contract (#3) |
| 10 | #21 | Reader plug socket | Reader contract (#3) |
| 11 | #20 | Split text into pieces and save them. DB | Plug socket (#21), the database (#12) |
| 12 | #22b | Page viewer that draws a box on the page | Page pictures (#18), text pieces (#20) |
| 13 | #25, #26, #24 | Tests: same file twice, broken file, fifty files | The steps above |
| 14 | #27, #31, #32 | Checks green on every pull request, two short docs | All sprint |

I put the plug socket (#21) before the text pieces (#20), so the text always comes
through the socket. CLAUDE.md says no code may call a reader directly.

**Done when.** Each issue's acceptance criteria are on the issue. I copy them into
each pull request and tick them there.

**How long.** My guess is 7 to 9 working days for all of it. About 4 days are left
(Thu 24 to Tue 29 Sep), and Day 5 is also Vrushit's testing. So it will not all fit.
See section 8. I will split my guess per task after the review.

---

## 5. Decisions I am making myself

- I fingerprint files with SHA-256, which comes with Python. No new library.
- Each step is its own small piece of code, and each issue is its own pull request under about 300 lines.
- Tests go in the same pull request as the code.
- Messages and logs never show file contents or file names.
- My test files are small files I make myself. No real documents go into the repo.

## 6. Things I need approved before I start

| What | Why | Approved |
|---|---|---|
| Database design (#1) and the customer separation rule (#2) | I don't know yet how the database will be built, and I must not design it myself. Upload, page pictures and text pieces all need it. | [ ] |
| Duplicates checked per customer only | If we checked across customers, customer B would learn that customer A has the same file. | [ ] |
| Reader contract (#3), including how positions are written | Text extraction (#19), the plug socket (#21), text pieces (#20) and the viewer all use it. | [ ] |
| Local setup (#9) with stand ins for file storage, the queue and the virus scanner | I can't run upload or the worker without them. MinIO, from my notes, has the AGPL-3.0 licence, so CLAUDE.md does not allow it. | [ ] |
| Upload limits: max file size and which file types are allowed | Upload (#14) needs a test for a file that is too big. | [ ] |
| Libraries, each with name and licence: virus scanning, Office to PDF, photo conversion, straightening, PDF text with positions, page pictures, Excel, and PDF.js (4.2.67 or later, older versions have a security hole) | I can't build the virus check, file preparation, page pictures, text extraction or the screens without them. I have not picked any. | [ ] |

## 7. Questions

**I need these answered in the review.**

1. **Aadhaar and PAN.** This sprint saves text, but hiding identity numbers is planned for Sprint 2. Real invoices have GST numbers, and a GST number contains the full PAN. Should I build the hiding step before I save text (my choice), or should we use only made up files until Sprint 2?
2. **Database.** I don't understand yet how the database will be built. When will the design (#1, #2) be ready? Can we go through it together?
3. **Who is uploading.** There is no login. How does the upload know which customer it is? The server has to decide this, not the browser, or anyone could change the customer id.
4. **Virus check.** Does it run during upload, or as the first step in the worker? Where do rejected files go?
5. **Coordinates.** I don't understand coordinates yet. Can you explain how we write down "where on the page" a piece of text is? Measured from the top left or the bottom left? In points or pixels? One box for each line, or for each word?
6. **Scans in Sprint 1.** Sprint 1 can't read scans. If a real sample is a scan, is it fine that it is only saved and marked "needs a reader"?
7. **Screens.** The file list and the viewer need the backend to list files and return a page. No issue covers that. Is it part of #22?
8. **Separation test in CI.** In CI the database user is a superuser, and the same user creates the tables, so it owns them. PostgreSQL lets superusers and table owners skip the customer separation rules, so the test would never really check them. Should the test use the restricted app role from #12, one that does not own the tables? I have asked this on #12 too.
9. **Where Day 5 testing runs.** On my machine or on the test environment? Can the test environment hold real documents?
10. **Please review my idea for later sprints.** This is my picture of the review and correction flow. It is not in the plan.
    - A file is uploaded, either a PDF or a phone photo.
    - The reader takes out the text and flags words it is not sure about.
    - A person clicks a flagged word and types the right one.
    - The fix changes only the saved text and the search data. The original file is never changed.
    - Each document remembers how it arrived. A phone photo can be taken again, a PDF cannot.
    - We keep the old text next to every fix, with who fixed it and when.

    Does this match what you want for Sprint 3? If yes, should Sprint 1 already remember how a file arrived, and keep the original file unchanged?

## 8. What could make this slip

- My guess is 7 to 9 days of work, and about 4 days are left.
- I am waiting for the database design, the local setup and library approvals. If they are late, my work is late too.
- File preparation (#17) needs the most libraries.
- If time runs out, I would move straightening crooked scans to Sprint 2 first, because Sprint 1 does not read scans. I need your yes for that.
- I will never drop the virus check, the page pictures, the plug socket or the customer separation test.

---

## 9. Before I start, I confirm

- [ ] I have read CLAUDE.md and CONTRIBUTING.md in this sprint, not just once months ago
- [ ] Every issue I listed has acceptance criteria, and I understand each one
- [ ] I know which of my tasks touch the database or customer separation
- [ ] I know what CI will check, and I can run those checks locally before opening a pull request

---

## Words used here

| Word | Meaning |
|---|---|
| Fingerprint | A short code made from the file's contents. The same file always gives the same code, so we can spot duplicates. |
| Duplicate | The same file uploaded again by the same customer. We keep one copy. |
| Queue | A waiting line of files to be processed, one job per file. |
| Worker | The program that takes jobs from the queue and processes the files. |
| Failure bin | Where a job goes after it fails a few times, so it does not block the others. |
| Reader | Anything that reads text from a page, such as direct reading of a PDF, or an AI for scans later. |
| Plug socket | One fixed way for every reader to connect, so a reader can be swapped without changing anything else. |
| Reader contract | The written rule for what a reader receives and returns. Vrushit writes it (#3). |
| Text piece | A small part of a document's text, saved with its page and position. Answers point at these later. |
| Position, coordinates | Where on the page a piece of text sits, written as a box. |
| Customer separation | One customer can never see another customer's files or data. |
| DB | The task touches the database, so it needs Vrushit's OK on a written plan first. |
| CI | The automatic checks that run on every pull request. |
| UAT | Vrushit's own testing on Day 5, before he signs the sprint off. |

---

## Vrushit's review

**Approach:** Approved | Changes needed
**Answers to the questions above:**
**Changes I want to the plan:**
**Anything I am adding or removing from the sprint:**

**Approved on:**
