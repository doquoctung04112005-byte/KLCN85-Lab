"""Small, dependency-free text previews for private Office documents."""

from posixpath import normpath
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _xml(archive, path):
    return ElementTree.fromstring(archive.read(path))


def docx_preview(file_obj):
    """Return ordered paragraphs and tables, without rendering document markup."""
    with ZipFile(file_obj) as archive:
        root = _xml(archive, "word/document.xml")
    body = root.find(f".//{{{WORD_NS}}}body")
    if body is None:
        return []

    blocks = []
    for child in body:
        if child.tag == f"{{{WORD_NS}}}p":
            text = "".join(node.text or "" for node in child.iter(f"{{{WORD_NS}}}t"))
            if text.strip():
                blocks.append({"kind": "paragraph", "text": text})
        elif child.tag == f"{{{WORD_NS}}}tbl":
            rows = []
            for row in child.findall(f"{{{WORD_NS}}}tr"):
                rows.append([
                    "".join(node.text or "" for node in cell.iter(f"{{{WORD_NS}}}t"))
                    for cell in row.findall(f"{{{WORD_NS}}}tc")
                ])
            if rows:
                blocks.append({"kind": "table", "rows": rows})
    return blocks


def _column_index(cell_reference):
    index = 0
    for char in cell_reference:
        if not char.isalpha():
            break
        index = index * 26 + ord(char.upper()) - ord("A") + 1
    return max(index - 1, 0)


def xlsx_preview(file_obj):
    """Return workbook sheets as plain cell values suitable for escaped HTML."""
    with ZipFile(file_obj) as archive:
        workbook = _xml(archive, "xl/workbook.xml")
        relationships = _xml(archive, "xl/_rels/workbook.xml.rels")
        targets = {
            relation.attrib["Id"]: relation.attrib["Target"]
            for relation in relationships.findall(f"{{{PKG_REL_NS}}}Relationship")
        }
        try:
            shared_root = _xml(archive, "xl/sharedStrings.xml")
            shared_strings = [
                "".join(part.text or "" for part in item.iter(f"{{{SHEET_NS}}}t"))
                for item in shared_root.findall(f"{{{SHEET_NS}}}si")
            ]
        except KeyError:
            shared_strings = []

        sheets = []
        for sheet in workbook.findall(f".//{{{SHEET_NS}}}sheet"):
            relation_id = sheet.attrib.get(f"{{{REL_NS}}}id")
            target = targets.get(relation_id)
            if not target:
                continue
            sheet_path = normpath(target.lstrip("/") if target.startswith("/") else f"xl/{target}")
            root = _xml(archive, sheet_path)
            rows = []
            for row_node in root.findall(f".//{{{SHEET_NS}}}sheetData/{{{SHEET_NS}}}row"):
                cells = {}
                for cell in row_node.findall(f"{{{SHEET_NS}}}c"):
                    reference = cell.attrib.get("r", "A1")
                    index = _column_index(reference)
                    value_node = cell.find(f"{{{SHEET_NS}}}v")
                    inline_node = cell.find(f"{{{SHEET_NS}}}is")
                    value = value_node.text if value_node is not None else ""
                    if cell.attrib.get("t") == "s" and value:
                        try:
                            value = shared_strings[int(value)]
                        except (ValueError, IndexError):
                            value = ""
                    elif cell.attrib.get("t") == "inlineStr" and inline_node is not None:
                        value = "".join(
                            part.text or "" for part in inline_node.iter(f"{{{SHEET_NS}}}t")
                        )
                    cells[index] = value or ""
                if cells:
                    rows.append([cells.get(index, "") for index in range(max(cells) + 1)])
            sheets.append({"name": sheet.attrib.get("name", "Trang tính"), "rows": rows})
    return sheets


def office_preview(file_type, file_obj):
    try:
        return ("docx", docx_preview(file_obj)) if file_type == "docx" else ("xlsx", xlsx_preview(file_obj))
    except (BadZipFile, KeyError, ElementTree.ParseError, OSError, ValueError):
        return file_type, None
