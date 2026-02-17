"""
script.py - Extract content from a Word document and generate README.md with images.

This script reads 'Implementing Virtual Networking word.docx', extracts all text
(headings, paragraphs, lists, tables) and images, then produces a GitHub-ready
README.md with images saved in an 'images/' folder.
"""

import os
import re
from docx import Document
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH


# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOCX_FILE = os.path.join(SCRIPT_DIR, "Implementing Virtual Networking word.docx")
README_FILE = os.path.join(SCRIPT_DIR, "README.md")
IMAGES_DIR = os.path.join(SCRIPT_DIR, "images")


# ── Helpers ────────────────────────────────────────────────────────────────────

def ensure_images_dir():
    """Create images directory if it doesn't exist."""
    os.makedirs(IMAGES_DIR, exist_ok=True)


def extract_all_images(doc):
    """
    Extract every image from the docx media folder and save to images/.
    Returns a dict mapping rId -> relative image path.
    """
    ensure_images_dir()
    image_map = {}  # rId -> 'images/imageN.ext'

    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            image_part = rel.target_part
            ext = os.path.splitext(image_part.partname)[1]  # e.g. .png, .jpeg
            image_filename = f"image{len(image_map) + 1}{ext}"
            image_path = os.path.join(IMAGES_DIR, image_filename)
            with open(image_path, "wb") as f:
                f.write(image_part.blob)
            image_map[rel.rId] = f"images/{image_filename}"

    return image_map


def get_images_in_paragraph(paragraph, image_map):
    """Return list of image markdown refs found in a paragraph's XML."""
    images = []
    for run in paragraph.runs:
        run_xml = run._element
        drawings = run_xml.findall(f".//{qn('wp:inline')}") + run_xml.findall(f".//{qn('wp:anchor')}")
        for drawing in drawings:
            blip = drawing.find(f".//{qn('a:blip')}")
            if blip is not None:
                rId = blip.get(qn("r:embed"))
                if rId and rId in image_map:
                    images.append(f"![image]({image_map[rId]})")
    return images


def run_has_formatting(run):
    """Check if a run has bold or italic."""
    bold = run.bold
    italic = run.italic
    return bold, italic


def format_run_text(run):
    """Wrap run text in markdown bold/italic as needed."""
    text = run.text
    if not text:
        return ""
    bold, italic = run_has_formatting(run)
    if bold and italic:
        return f"***{text}***"
    elif bold:
        return f"**{text}**"
    elif italic:
        return f"*{text}*"
    return text


def paragraph_to_markdown(paragraph, image_map):
    """
    Convert a single paragraph to markdown, handling:
      - Headings (Heading 1-6)
      - Lists (bullet, numbered)
      - Normal text with bold/italic
      - Inline images
    """
    style_name = paragraph.style.name if paragraph.style else ""
    
    # ── Build the text from runs with formatting ──
    text_parts = []
    inline_images = []

    for run in paragraph.runs:
        formatted = format_run_text(run)
        if formatted:
            text_parts.append(formatted)
        # Check for images in this run
        run_xml = run._element
        drawings = run_xml.findall(f".//{qn('wp:inline')}") + run_xml.findall(f".//{qn('wp:anchor')}")
        for drawing in drawings:
            blip = drawing.find(f".//{qn('a:blip')}")
            if blip is not None:
                rId = blip.get(qn("r:embed"))
                if rId and rId in image_map:
                    inline_images.append(f"![image]({image_map[rId]})")

    text = "".join(text_parts).strip()
    
    # ── Headings ──
    if style_name.startswith("Heading"):
        try:
            level = int(style_name.replace("Heading", "").strip())
        except ValueError:
            level = 1
        prefix = "#" * level
        result = f"{prefix} {text}" if text else ""
        if inline_images:
            result += "\n\n" + "\n\n".join(inline_images)
        return result

    # ── List items ──
    numPr = paragraph._element.find(f".//{qn('w:numPr')}")
    if numPr is not None:
        ilvl_elem = numPr.find(qn("w:ilvl"))
        indent_level = int(ilvl_elem.get(qn("w:val"), "0")) if ilvl_elem is not None else 0
        indent = "  " * indent_level

        numId_elem = numPr.find(qn("w:numId"))
        numId = numId_elem.get(qn("w:val"), "0") if numId_elem is not None else "0"
        
        # Heuristic: numId helps distinguish ordered vs unordered, but
        # since we can't easily resolve the abstractNum, we default to bullet.
        # Word typically uses numId=1 for bullets and higher for numbered lists.
        bullet = "-"
        result = f"{indent}{bullet} {text}" if text else ""
        if inline_images:
            result += "\n\n" + "\n\n".join(inline_images)
        return result

    # ── Normal paragraph ──
    result = text if text else ""
    if inline_images:
        if result:
            result += "\n\n" + "\n\n".join(inline_images)
        else:
            result = "\n\n".join(inline_images)
    return result


def table_to_markdown(table):
    """Convert a Word table to a Markdown table."""
    rows = table.rows
    if not rows:
        return ""

    md_rows = []
    for i, row in enumerate(rows):
        cells = [cell.text.strip().replace("|", "\\|") for cell in row.cells]
        md_rows.append("| " + " | ".join(cells) + " |")
        if i == 0:
            # Add separator row after header
            md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")

    return "\n".join(md_rows)


# ── Main ───────────────────────────────────────────────────────────────────────

def convert_docx_to_readme():
    """Main conversion function."""
    print(f"Reading: {DOCX_FILE}")
    doc = Document(DOCX_FILE)

    # 1. Extract all images first
    image_map = extract_all_images(doc)
    print(f"Extracted {len(image_map)} images to {IMAGES_DIR}/")

    # 2. Walk through the document body elements in order
    #    (paragraphs and tables are interleaved)
    md_lines = []
    body = doc.element.body

    for child in body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if tag == "p":
            # It's a paragraph
            from docx.text.paragraph import Paragraph
            para = Paragraph(child, doc)
            md = paragraph_to_markdown(para, image_map)
            if md:
                md_lines.append(md)
                md_lines.append("")  # blank line for spacing

        elif tag == "tbl":
            # It's a table
            from docx.table import Table
            tbl = Table(child, doc)
            md = table_to_markdown(tbl)
            if md:
                md_lines.append(md)
                md_lines.append("")  # blank line for spacing

    # 3. Write README.md
    readme_content = "\n".join(md_lines).strip() + "\n"

    # Clean up excessive blank lines (more than 2 consecutive)
    readme_content = re.sub(r"\n{3,}", "\n\n", readme_content)

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(readme_content)

    print(f"README.md written to: {README_FILE}")
    print("Done!")


if __name__ == "__main__":
    convert_docx_to_readme()
