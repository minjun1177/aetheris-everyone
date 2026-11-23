"""The Word / Excel files the app writes are real packages, and the readers read them back."""

import io
import os
import posixpath
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree

from aetheris_everyone import documents

_CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def check_package(test: unittest.TestCase, data: bytes, main_part: str) -> zipfile.ZipFile:
    """What Word and Excel insist on before opening a file at all."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    test.assertIsNone(archive.testzip())
    names = set(archive.namelist())
    for name in names:
        ElementTree.fromstring(archive.read(name))           # every part is well-formed XML
    types = ElementTree.fromstring(archive.read("[Content_Types].xml"))
    defaults = {d.get("Extension") for d in types.iter(f"{_CT}Default")}
    overrides = {o.get("PartName").lstrip("/") for o in types.iter(f"{_CT}Override")}
    for name in names:
        test.assertTrue(name in overrides or name.rsplit(".", 1)[-1] in defaults,
                        f"{name} has no content type")
    test.assertIn(main_part, overrides)
    for rels in (n for n in names if n.endswith(".rels")):
        base = posixpath.dirname(posixpath.dirname(rels))
        for rel in ElementTree.fromstring(archive.read(rels)).iter(f"{_REL}Relationship"):
            target = posixpath.normpath(posixpath.join(base, rel.get("Target")))
            test.assertIn(target, names, f"{rels} points at a missing {target}")
    return archive


def _zip(files: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class TempDir(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="aetheris-docs-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def save(self, name: str, data: bytes) -> str:
        path = os.path.join(self.dir, name)
        with open(path, "wb") as f:
            f.write(data)
        return path


class WordFiles(TempDir):
    def test_package_is_complete(self):
        data = documents.markdown_to_docx("# 제목\n\n본문 & <특수> \"문자\"\n- 항목\n1. 하나\n---\n"
                                          "| A | B |\n|---|---|\n| 1 | **2** |")
        archive = check_package(self, data, "word/document.xml")
        body = ElementTree.fromstring(archive.read("word/document.xml")).find(f"{_W}body")
        self.assertIsNotNone(body.find(f"{_W}tbl"))
        self.assertEqual(body[-1].tag, f"{_W}sectPr")       # Word wants sectPr last
        styles = ElementTree.fromstring(archive.read("word/styles.xml"))
        defined = {s.get(f"{_W}styleId") for s in styles.iter(f"{_W}style")}
        used = {p.get(f"{_W}val") for p in body.iter(f"{_W}pStyle")} | \
               {p.get(f"{_W}val") for p in body.iter(f"{_W}tblStyle")}
        self.assertLessEqual(used, defined)

    def test_round_trip_keeps_text_and_headings(self):
        path = self.save("a.docx", documents.markdown_to_docx(
            "# 보고서\n## 요약\n매출 **10%** 증가 & 비용 <감소>\n- 첫째\n| 항목 | 값 |\n|---|---|\n| 커피 | 4500 |"))
        text = documents.extract(path)
        for expected in ("# 보고서", "## 요약", "매출 10% 증가 & 비용 <감소>", "• 첫째", "커피", "4500"):
            self.assertIn(expected, text)

    def test_damaged_file_is_a_clear_error(self):
        path = self.save("broken.docx", b"not a zip")
        with self.assertRaises(ValueError) as caught:
            documents.extract(path)
        self.assertIn("damaged", str(caught.exception))


class ExcelFiles(TempDir):
    def test_package_is_complete(self):
        data = documents.rows_to_xlsx([["a", "b"], ["1", "x & <y>"]])
        check_package(self, data, "xl/workbook.xml")

    def test_round_trip(self):
        rows = [["날짜", "항목", "금액", "메모"],
                ["2026-11-01", "커피", "4500", "a, \"quoted\""],
                ["2026-11-02", "점심", "12,000", ""],
                ["", "", "007", "<tag> & more"]]
        path = self.save("t.xlsx", documents.rows_to_xlsx(rows))
        text = documents.extract(path)
        lines = [line for line in text.splitlines() if line]
        self.assertEqual(lines[0], "## Sheet: Sheet1")
        self.assertEqual(lines[1], "날짜,항목,금액,메모")
        self.assertEqual(lines[2], '2026-11-01,커피,4500,"a, ""quoted"""')
        self.assertEqual(lines[3], "2026-11-02,점심,12000")       # a number; empty last cell not stored
        self.assertEqual(lines[4], ",,007,<tag> & more")          # leading zero stays text

    def test_wide_sheet_uses_two_letter_columns(self):
        rows = [[f"c{n}" for n in range(30)], [str(n) for n in range(30)]]
        archive = zipfile.ZipFile(io.BytesIO(documents.rows_to_xlsx(rows)))
        sheet = archive.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn('r="AD2"', sheet)
        path = self.save("w.xlsx", documents.rows_to_xlsx(rows))
        self.assertIn("c29", documents.extract(path))

    def test_formula_is_a_formula(self):
        archive = zipfile.ZipFile(io.BytesIO(documents.rows_to_xlsx([["n"], ["1"], ["=SUM(A2:A2)"]])))
        self.assertIn("<f>SUM(A2:A2)</f>", archive.read("xl/worksheets/sheet1.xml").decode())

    def test_text_to_rows_formats(self):
        self.assertEqual(documents.text_to_rows("| a | b |\n|---|---|\n| 1 | 2 |"), [["a", "b"], ["1", "2"]])
        self.assertEqual(documents.text_to_rows("a\tb\n1\t2"), [["a", "b"], ["1", "2"]])
        self.assertEqual(documents.text_to_rows('a,"b,c"\n1,2'), [["a", "b,c"], ["1", "2"]])
        with self.assertRaises(ValueError):
            documents.render("x.xlsx", "   \n")


class OtherReaders(TempDir):
    def test_pptx_and_hwpx(self):
        a = "http://schemas.openxmlformats.org/drawingml/2006/main"
        slide = f'<p:sld xmlns:p="p" xmlns:a="{a}"><a:p><a:r><a:t>슬라이드 제목</a:t></a:r></a:p></p:sld>'
        path = self.save("s.pptx", _zip({"ppt/slides/slide2.xml": slide, "ppt/slides/slide10.xml": slide}))
        self.assertEqual(documents.extract(path).count("슬라이드 제목"), 2)
        section = '<hs:sec xmlns:hs="h" xmlns:hp="p"><hp:p><hp:run><hp:t>한글 문서</hp:t></hp:run></hp:p></hs:sec>'
        path = self.save("h.hwpx", _zip({"Contents/section0.xml": section}))
        self.assertEqual(documents.extract(path), "한글 문서")

    def test_unknown_type(self):
        with self.assertRaises(ValueError):
            documents.extract(self.save("a.odt", b""))


@unittest.skipUnless(shutil.which("soffice"), "LibreOffice is not installed")
class OpensInAnOfficeSuite(TempDir):
    """With LibreOffice present, prove the files open by converting them."""

    def test_converts(self):
        for name, data in (("r.docx", documents.markdown_to_docx("# 제목\n| a | b |\n|---|---|\n| 1 | 2 |")),
                           ("r.xlsx", documents.rows_to_xlsx([["a", "b"], ["1", "2"]]))):
            path = self.save(name, data)
            subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", self.dir, path],
                           check=True, capture_output=True, timeout=120)
            self.assertTrue(os.path.getsize(os.path.splitext(path)[0] + ".pdf") > 0)


if __name__ == "__main__":
    unittest.main()
