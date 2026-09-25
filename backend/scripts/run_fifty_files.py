"""Run fifty mixed files through the whole Sprint 1 pipeline (issue #24).

    cd backend
    python -m scripts.run_fifty_files

Every file is made up here; no real document is used. The run uses the
in-memory stand-ins from tests/, so it measures this code only, not a real
database, storage, queue or scanner. Timings are therefore a floor, not a
forecast.

The report lists every outcome, explains every failure in plain words, and
records timings for upload and processing (median, 95th percentile, max).
"""

import io
import statistics
import time
from collections import Counter
from dataclasses import dataclass

from kaagaz.ingestion import sniff
from kaagaz.ingestion.errors import UploadRejected
from kaagaz.ingestion.policy import UploadPolicy
from kaagaz.ingestion.service import UploadService
from kaagaz.jobs.worker import Worker
from kaagaz.masking.identity import IndianIdMasker
from kaagaz.pipeline import DocumentProcessor
from kaagaz.reading.csv_reader import CsvReader
from kaagaz.reading.socket import ReaderSocket
from kaagaz.reading.xlsx_reader import XlsxLimits, XlsxReader
from kaagaz.scanning.gate import DocumentStatus, ScanGate, Verdict
from tests.fakes import MemoryPieces, MemoryRepository, MemoryStatuses, MemoryStorage
from tests.lease_queue import FakeClock, LeaseQueue
from tests.xlsx_builder import make_xlsx, make_zip, sheet_xml

CUSTOMER = "cust-demo"
FAKE_VIRUS_MARKER = b"FAKE-VIRUS-FOR-TESTING"

# What each outcome means, for the report.
EXPLAIN = {
    "ready": "read and split into pieces",
    "needs_reader": "stored and scanned; waits for the Sprint 2 reader or file preparation (#17)",
    "duplicate": "same bytes already uploaded by this customer; stored once",
    "rejected:empty_file": "refused at upload: the file is empty",
    "rejected:too_large": "refused at upload: over the size limit",
    "rejected:unsupported_type": "refused at upload: type not recognised from its first bytes",
    "failed:virus_found": "failed the virus scan; quarantined and never read",
    "failed:malformed_csv": "a CSV with a broken quote; nothing kept",
    "failed:corrupt_file": "a damaged spreadsheet; nothing kept",
}


class MarkerScanner:
    """Stand-in scanner: files containing the fake marker count as infected."""

    def scan(self, data: bytes) -> Verdict:
        return Verdict.INFECTED if FAKE_VIRUS_MARKER in data else Verdict.CLEAN


@dataclass
class Sample:
    name: str
    data: bytes


def make_samples() -> list[Sample]:
    samples = []
    for i in range(18):
        rows = "".join(f"INV-{i}-{r},{(r + 1) * 100}\n" for r in range(i * 5 + 1))
        samples.append(Sample(f"invoices_{i}.csv", f"invoice,amount\n{rows}".encode()))
    for i in range(10):
        cells = "".join(
            f'<row r="{r}"><c r="A{r}" t="inlineStr"><is><t>Item {r}</t></is></c><c r="B{r}"><v>{r * 10}</v></c></row>'
            for r in range(1, i * 20 + 2)
        )
        samples.append(Sample(f"register_{i}.xlsx", make_xlsx([("Register", sheet_xml(cells))])))
    samples += [Sample(f"scan_{i}.pdf", b"%PDF-1.7\n" + bytes(range(256)) * (i + 1)) for i in range(8)]
    samples += [Sample(f"photo_{i}.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * (500 * (i + 1))) for i in range(4)]
    samples += [Sample(f"letter_{i}.docx", make_zip({"word/document.xml": b"<document/>" * (i + 1)})) for i in range(3)]
    samples += [
        Sample("broken_quote.csv", b'a,"never closed\n'),
        Sample("damaged.xlsx", make_xlsx([("S", sheet_xml('<row r="1"><c r="A0"><v>1</v></c></row>'))])),
        Sample("empty.csv", b""),
        Sample("huge.csv", b"a," * 60_000),
        Sample("program.bin", b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 100),
        Sample("infected.csv", b"note\n" + FAKE_VIRUS_MARKER + b"\n"),
        Sample("invoices_0_again.csv", samples[0].data),  # a duplicate
    ]
    return samples


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def main() -> None:
    clock = FakeClock()
    queue = LeaseQueue(clock, lease_seconds=30, max_attempts=3)
    repo, storage, statuses, pieces = MemoryRepository(), MemoryStorage(), MemoryStatuses(), MemoryPieces()
    policy = UploadPolicy(max_bytes=100_000, allowed_types=frozenset(sniff.KNOWN_TYPES))
    upload = UploadService(policy, repo, storage, queue)
    socket = ReaderSocket({
        sniff.TEXT: CsvReader(max_cells=100_000),
        sniff.ZIP: XlsxReader(XlsxLimits(max_entries=200, max_member_bytes=5_000_000,
                                         max_total_bytes=20_000_000, max_cells=100_000)),
    })
    gate = ScanGate(storage, MarkerScanner(), storage, statuses)
    worker = Worker(queue, DocumentProcessor(gate, statuses, repo, socket, IndianIdMasker(), pieces))

    samples = make_samples()
    outcomes: dict[str, str] = {}
    documents: dict[str, str] = {}
    upload_ms: list[float] = []
    for sample in samples:
        started = time.perf_counter()
        try:
            result = upload.accept(CUSTOMER, io.BytesIO(sample.data))
        except UploadRejected as rejected:
            outcomes[sample.name] = f"rejected:{rejected.code.value}"
            continue
        finally:
            upload_ms.append((time.perf_counter() - started) * 1000)
        if result.duplicate:
            outcomes[sample.name] = "duplicate"
        else:
            documents[result.document_id] = sample.name

    process_ms: list[float] = []
    while True:
        started = time.perf_counter()
        if not worker.run_once():
            break
        process_ms.append((time.perf_counter() - started) * 1000)

    failed_codes = {f.job.document_id: f.code for f in queue.failed.values()}
    for document_id, name in documents.items():
        if document_id in failed_codes:
            outcomes[name] = f"failed:{failed_codes[document_id]}"
        else:
            status = statuses.get_status(CUSTOMER, document_id)
            outcomes[name] = status.value if isinstance(status, DocumentStatus) else "unknown"

    counts = Counter(outcomes.values())
    total_pieces = sum(len(pieces.for_document(CUSTOMER, d)) for d in documents)
    print(f"Files: {len(samples)}   documents stored: {len(documents)}   pieces: {total_pieces}\n")
    print(f"{'Outcome':<28} {'Files':>5}  Meaning")
    for outcome, count in sorted(counts.items()):
        print(f"{outcome:<28} {count:>5}  {EXPLAIN.get(outcome, 'NOT EXPLAINED: investigate')}")
    print()
    for label, values in (("Upload", upload_ms), ("Process (per job)", process_ms)):
        print(f"{label:<18} median {statistics.median(values):7.2f} ms   "
              f"p95 {percentile(values, 0.95):7.2f} ms   max {max(values):7.2f} ms   n={len(values)}")
    unexplained = [o for o in counts if o not in EXPLAIN]
    print("\nEvery outcome explained." if not unexplained else f"\nUNEXPLAINED outcomes: {unexplained}")


if __name__ == "__main__":
    main()
