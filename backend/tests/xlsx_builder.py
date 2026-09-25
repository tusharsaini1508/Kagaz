"""Build small .xlsx files in memory for tests, with the standard zipfile.

Deliberately independent of the reader: column letters and XML are written
out by hand here, never produced by the code under test.
"""

import io
import zipfile

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def sheet_xml(cells_xml: str) -> str:
    """A worksheet whose <sheetData> holds ``cells_xml`` (rows and cells)."""
    return f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{MAIN_NS}"><sheetData>{cells_xml}</sheetData></worksheet>'


def make_xlsx(
    sheets: list[tuple[str, str]],
    shared_strings: list[str] | None = None,
    *,
    extra_parts: dict[str, bytes] | None = None,
    workbook_ns: str = MAIN_NS,
    rels_target_prefix: str = "worksheets/",
) -> bytes:
    """``sheets`` is [(sheet name, worksheet XML)], in workbook order.

    Sheet parts are written in reverse order under names that do not match
    their position, so a reader must follow the workbook and its
    relationships, not the part names.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        sheet_entries, rels = [], []
        for index, (name, xml) in enumerate(sheets, start=1):
            part = f"sheet{100 - index}.xml"
            archive.writestr(f"xl/worksheets/{part}", xml)
            sheet_entries.append(f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>')
            rels.append(
                f'<Relationship Id="rId{index}" Type="worksheet" Target="{rels_target_prefix}{part}"/>'
            )
        archive.writestr(
            "xl/workbook.xml",
            f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{workbook_ns}" xmlns:r="{REL_NS}">'
            f"<sheets>{''.join(sheet_entries)}</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{PKG_NS}">{"".join(rels)}</Relationships>',
        )
        if shared_strings is not None:
            items = "".join(f"<si><t>{text}</t></si>" for text in shared_strings)
            archive.writestr(
                "xl/sharedStrings.xml",
                f'<?xml version="1.0" encoding="UTF-8"?><sst xmlns="{MAIN_NS}">{items}</sst>',
            )
        for name, content in (extra_parts or {}).items():
            archive.writestr(name, content)
    return buffer.getvalue()


def make_zip(parts: dict[str, bytes], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return buffer.getvalue()
