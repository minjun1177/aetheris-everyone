"""Office documents as text, and simple Word / Excel files from text.

People keep their work in .docx, .xlsx, .pptx, .hwpx and .pdf, not in .txt.
Reading uses only the standard library (they are zip files of XML) except PDF,
which uses `pypdf` when it is installed. Writing turns the markdown or table a
model naturally produces into a real Word or Excel file, so "make it a Word
document" works with the same `write_file` call as any other file.
"""

import csv
import html
import io
import re
import zipfile
from xml.etree import ElementTree

TEXT_LIMIT = 200_000

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

READABLE = (".docx", ".xlsx", ".pptx", ".hwpx", ".pdf")
WRITABLE = (".docx", ".xlsx")


def _xml(archive: zipfile.ZipFile, name: str):
    return ElementTree.fromstring(archive.read(name))


def _docx(path: str) -> str:
    with zipfile.ZipFile(path) as archive:
        root = _xml(archive, "word/document.xml")
    lines = []
    for paragraph in root.iter(f"{_W}p"):
        text = "".join(("\t" if node.tag == f"{_W}tab" else node.text or "")
                       for node in paragraph.iter() if node.tag in (f"{_W}t", f"{_W}tab"))
        style = paragraph.find(f"{_W}pPr/{_W}pStyle")
        level = ""
        if style is not None:
            match = re.search(r"(\d)", style.get(f"{_W}val", ""))
            if "heading" in style.get(f"{_W}val", "").lower() and match:
                level = "#" * int(match.group(1)) + " "
        lines.append(level + text if text else "")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _column_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref or "A")
    index = 0
    for char in letters.group(0) if letters else "A":
        index = index * 26 + (ord(char) - 64)
    return index - 1


def _xlsx(path: str) -> str:
    out = []
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            for item in _xml(archive, "xl/sharedStrings.xml").iter(f"{_S}si"):
                shared.append("".join(t.text or "" for t in item.iter(f"{_S}t")))
        workbook = _xml(archive, "xl/workbook.xml")
        names = [s.get("name") for s in workbook.iter(f"{_S}sheet")]
        sheets = sorted((n for n in archive.namelist()
                         if re.match(r"xl/worksheets/sheet\d+\.xml$", n)),
                        key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
        for number, sheet in enumerate(sheets):
            title = names[number] if number < len(names) else f"Sheet{number + 1}"
            out.append(f"## Sheet: {title}")
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            for row in _xml(archive, sheet).iter(f"{_S}row"):
                cells = {}
                for cell in row.iter(f"{_S}c"):
                    kind = cell.get("t")
                    value = cell.find(f"{_S}v")
                    text = value.text if value is not None else ""
                    if kind == "s" and text:
                        text = shared[int(text)] if int(text) < len(shared) else ""
                    elif kind == "inlineStr":
                        text = "".join(t.text or "" for t in cell.iter(f"{_S}t"))
                    cells[_column_index(cell.get("r", ""))] = text or ""
                if cells:
                    writer.writerow([cells.get(i, "") for i in range(max(cells) + 1)])
            out.append(buffer.getvalue().strip())
    return "\n\n".join(out)


def _pptx(path: str) -> str:
    out = []
    with zipfile.ZipFile(path) as archive:
        slides = sorted((n for n in archive.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                        key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
        for number, slide in enumerate(slides, 1):
            root = _xml(archive, slide)
            paragraphs = ["".join(t.text or "" for t in p.iter(f"{_A}t"))
                          for p in root.iter(f"{_A}p")]
            out.append(f"## Slide {number}\n" + "\n".join(p for p in paragraphs if p.strip()))
    return "\n\n".join(out)


def _hwpx(path: str) -> str:
    out = []
    with zipfile.ZipFile(path) as archive:
        sections = sorted(n for n in archive.namelist()
                          if re.match(r"Contents/section\d+\.xml$", n))
        for section in sections:
            root = _xml(archive, section)
            for node in root.iter():
                if node.tag.endswith("}p"):
                    text = "".join(t.text or "" for t in node.iter() if t.tag.endswith("}t"))
                    out.append(text)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _pdf(path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("PDF reading is not available in this installation") from None
    reader = PdfReader(path)
    pages = []
    for number, page in enumerate(reader.pages, 1):
        pages.append(f"## Page {number}\n{(page.extract_text() or '').strip()}")
        if sum(len(p) for p in pages) > TEXT_LIMIT:
            break
    text = "\n\n".join(pages)
    if not text.replace("## Page", "").strip(" \n0123456789"):
        return "(This PDF has no text layer - it is probably a scanned image.)"
    return text


def extract(path: str) -> str:
    """Text of an office document or PDF. Raises ValueError when it cannot."""
    ext = path.lower().rsplit(".", 1)[-1]
    try:
        reader = {"docx": _docx, "xlsx": _xlsx, "pptx": _pptx, "hwpx": _hwpx, "pdf": _pdf}[ext]
    except KeyError:
        raise ValueError(f".{ext} is not a document type this can read") from None
    try:
        return reader(path)[:TEXT_LIMIT]
    except ValueError:
        raise
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise ValueError(f"the file looks damaged or is not a real .{ext} ({error})") from None
    except Exception as error:
        # pypdf's own errors (PdfReadError, PdfStreamError ...) are not ValueErrors; one
        # damaged PDF must not end a whole search or turn.
        if ext != "pdf":
            raise
        raise ValueError(f"the PDF looks damaged or is protected ({type(error).__name__})") from None


# -- writing -----------------------------------------------------------------

def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _runs(text: str) -> str:
    """Inline **bold** and *italic* as Word runs."""
    out = []
    for piece in re.split(r"(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)", text):
        if not piece:
            continue
        props = ""
        if piece.startswith("**") and piece.endswith("**") and len(piece) > 4:
            piece, props = piece[2:-2], "<w:rPr><w:b/></w:rPr>"
        elif piece.startswith("*") and piece.endswith("*") and len(piece) > 2:
            piece, props = piece[1:-1], "<w:rPr><w:i/></w:rPr>"
        out.append(f'<w:r>{props}<w:t xml:space="preserve">{_esc(piece)}</w:t></w:r>')
    return "".join(out)


def _paragraph(text: str, style: str = "") -> str:
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{props}{_runs(text)}</w:p>"


def _table(rows: list) -> str:
    width = max(len(r) for r in rows)
    out = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/>'
           '<w:tblBorders>' + "".join(
               f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="999999"/>'
               for side in ("top", "left", "bottom", "right", "insideH", "insideV")) +
           '</w:tblBorders></w:tblPr>']
    for number, row in enumerate(rows):
        out.append("<w:tr>")
        for cell in row + [""] * (width - len(row)):
            text = f"**{cell}**" if number == 0 and cell else cell
            out.append(f"<w:tc><w:p>{_runs(text)}</w:p></w:tc>")
        out.append("</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


def _table_row(line: str) -> list:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def markdown_to_docx(text: str) -> bytes:
    body = []
    lines = text.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            rows = [_table_row(line)]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_table_row(lines[i]))
                i += 1
            body.append(_table(rows))
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)", stripped)
        if heading:
            body.append(_paragraph(heading.group(2), f"Heading{len(heading.group(1))}"))
        elif re.match(r"^[-*•]\s+", stripped):
            body.append(_paragraph("• " + re.sub(r"^[-*•]\s+", "", stripped), "ListParagraph"))
        elif re.match(r"^\d+[.)]\s+", stripped):
            body.append(_paragraph(stripped, "ListParagraph"))
        elif stripped in ("---", "***"):
            body.append("<w:p/>")
        else:
            body.append(_paragraph(line.rstrip()))
        i += 1

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body>{"".join(body)}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>'
        '</w:body></w:document>')
    heading_styles = "".join(
        f'<w:style w:type="paragraph" w:styleId="Heading{n}"><w:name w:val="heading {n}"/>'
        f'<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/>'
        f'<w:spacing w:before="{360 - n * 40}" w:after="120"/><w:outlineLvl w:val="{n - 1}"/></w:pPr>'
        f'<w:rPr><w:b/><w:sz w:val="{40 - n * 6}"/></w:rPr></w:style>' for n in range(1, 5))
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Malgun Gothic" '
        'w:hAnsi="Malgun Gothic" w:eastAsia="Malgun Gothic"/><w:sz w:val="22"/></w:rPr>'
        '</w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="300" '
        'w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/>'
        '<w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="400"/></w:pPr></w:style>'
        '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/></w:style>'
        + heading_styles + '</w:styles>')
    files = {
        "[Content_Types].xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.wordprocessingml.styles+xml"/></Types>',
        "_rels/.rels":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/_rels/document.xml.rels":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/styles" Target="styles.xml"/></Relationships>',
        "word/document.xml": document,
        "word/styles.xml": styles,
    }
    return _zip(files)


def _zip(files: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def text_to_rows(text: str) -> list:
    """A markdown table, CSV or tab-separated text, as rows of cells."""
    lines = [line for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    if lines and lines[0].strip().startswith("|"):
        return [_table_row(line) for line in lines
                if not re.match(r"^\s*\|?\s*:?-{2,}", line)]
    if lines and "\t" in lines[0]:
        return [line.split("\t") for line in lines]
    return [row for row in csv.reader(lines)]


def _cell_ref(row: int, column: int) -> str:
    letters = ""
    column += 1
    while column:
        column, rest = divmod(column - 1, 26)
        letters = chr(65 + rest) + letters
    return f"{letters}{row + 1}"


def _number(value: str):
    cleaned = value.replace(",", "").strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", cleaned) and not (len(cleaned) > 1 and cleaned[0] == "0"
                                                        and cleaned[1] != "."):
        return cleaned
    return None


def rows_to_xlsx(rows: list) -> bytes:
    sheet_rows = []
    for r, row in enumerate(rows):
        cells = []
        for c, value in enumerate(row):
            value = str(value)
            ref = _cell_ref(r, c)
            style = ' s="1"' if r == 0 else ""
            number = _number(value) if r else None
            if value.startswith("="):
                cells.append(f'<c r="{ref}"{style}><f>{_esc(value[1:])}</f></c>')
            elif number is not None:
                cells.append(f'<c r="{ref}"{style}><v>{number}</v></c>')
            elif value:
                cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t xml:space="preserve">'
                             f'{_esc(value)}</t></is></c>')
        sheet_rows.append(f'<row r="{r + 1}">{"".join(cells)}</row>')
    widths = ""
    if rows:
        columns = max(len(row) for row in rows)
        widths = "<cols>" + "".join(
            f'<col min="{c + 1}" max="{c + 1}" width="'
            f'{min(60, max(10, max((len(str(row[c])) if c < len(row) else 0) for row in rows) * 1.6))}'
            f'" customWidth="1"/>' for c in range(columns)) + "</cols>"
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    files = {
        "[Content_Types].xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.'
            'openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.styles+xml"/></Types>',
        "_rels/.rels":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/_rels/workbook.xml.rels":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/styles" Target="styles.xml"/></Relationships>',
        "xl/workbook.xml":
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="{ns}" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/styles.xml":
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="{ns}">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
            '</styleSheet>',
        "xl/worksheets/sheet1.xml":
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="{ns}">'
            f'{widths}<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>',
    }
    return _zip(files)


def render(path: str, text: str) -> bytes:
    """The bytes to write for `text` saved under `path`'s document type."""
    if path.lower().endswith(".docx"):
        return markdown_to_docx(text)
    if path.lower().endswith(".xlsx"):
        rows = text_to_rows(text)
        if not rows:
            raise ValueError("no table rows found - send CSV or a markdown table")
        return rows_to_xlsx(rows)
    raise ValueError("not a writable document type")
