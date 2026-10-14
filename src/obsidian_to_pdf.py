#!/usr/bin/env python3
"""
obsidian_to_pdf.py

Convert a folder of Obsidian Markdown files to a single clean PDF.
- Recursively processes all .md files
- Output filename is the folder name + .pdf
- Handles Obsidian wikilinks [[Note]] and embeds ![[image.png]]
- Resolves images from Obsidian's default Attachments/ folders
- Bold, inline/fenced code, numbered lists, circular bullets
- Markdown tables rendered as images
- Clean, readable typography
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

# Quiet noisy fontTools subset warnings (e.g. bdat/bloc tables) if any remain
logging.getLogger("fontTools.subset").setLevel(logging.ERROR)
logging.getLogger("fontTools.ttLib").setLevel(logging.ERROR)

import yaml
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

# Local cache for Unicode fonts (downloaded once)
FONT_CACHE_DIR = Path.home() / ".cache" / "obsidian_to_pdf_fonts"
NOTO_FONTS = {
    "": (
        "NotoSans-Regular.ttf",
        "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
    ),
    "B": (
        "NotoSans-Bold.ttf",
        "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf",
    ),
    "I": (
        "NotoSans-Italic.ttf",
        "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Italic.ttf",
    ),
    "BI": (
        "NotoSans-BoldItalic.ttf",
        "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-BoldItalic.ttf",
    ),
}

# Use core Courier for code to avoid TTF subset warnings (bdat/bloc/feat/morx).


def parse_frontmatter(raw: str) -> Tuple[dict, str]:
    """Parse YAML frontmatter from a markdown file manually."""
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
            except Exception:
                fm = {}
            return fm, parts[2]
    return {}, raw


def find_markdown_files(root: Path) -> List[Path]:
    """Recursively find all .md files, sorted by relative path."""
    return sorted(root.rglob("*.md"))


def get_title(frontmatter_data: dict, filepath: Path) -> str:
    """Extract title from frontmatter or fall back to filename."""
    title = frontmatter_data.get("title") or frontmatter_data.get("Title")
    if title:
        return str(title).strip()
    return filepath.stem


def convert_wikilinks(text: str) -> str:
    """Convert Obsidian wikilinks to plain text."""

    def replace_wikilink(match):
        return match.group(2) or match.group(1)

    return re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", replace_wikilink, text)


def resolve_attachment_path(
    embed_target: str, current_dir: Path, vault_root: Path
) -> Optional[Path]:
    """Resolve an Obsidian attachment/embed path."""
    target = Path(embed_target.strip())
    if target.is_absolute() and target.exists():
        return target

    candidates = [
        current_dir / target,
        current_dir / "Attachments" / target.name,
        current_dir.parent / "Attachments" / target.name,
        vault_root / "Attachments" / target.name,
        vault_root / target,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    for att_dir in vault_root.rglob("Attachments"):
        candidate = att_dir / target.name
        if candidate.exists():
            return candidate
    return None


def convert_obsidian_embeds(text: str, current_dir: Path, vault_root: Path) -> str:
    """Convert Obsidian embeds ![[...]] to internal markers or plain text."""

    def replace_embed(match):
        target = match.group(1).strip()
        alias = match.group(2).strip() if match.group(2) else None
        image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tiff"}
        ext = Path(target).suffix.lower()
        if ext in image_exts:
            return f"<<OBS_IMAGE:{target}>>"
        return alias or target

    return re.sub(r"!\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", replace_embed, text)


def preprocess_content(content: str, current_dir: Path, vault_root: Path) -> str:
    """Run Obsidian-specific conversions. Embeds before wikilinks."""
    content = convert_obsidian_embeds(content, current_dir, vault_root)
    content = convert_wikilinks(content)
    return content


def extract_callouts(text: str) -> str:
    """Convert basic Obsidian callouts to readable bold labels."""
    lines = text.splitlines(keepends=True)
    result = []
    i = 0
    callout_re = re.compile(r"^>\s*\[!(\w+)](?:\s*(.+))?$")

    while i < len(lines):
        line = lines[i]
        match = callout_re.match(line)
        if match:
            callout_type = match.group(1).capitalize()
            title = match.group(2) or ""
            result.append(f"**{callout_type}:** {title}\n")
            i += 1
            while i < len(lines) and lines[i].startswith(">"):
                result.append(lines[i][1:].lstrip())
                i += 1
            result.append("\n")
            continue
        result.append(line)
        i += 1
    return "".join(result)


def normalize_glyphs(text: str) -> str:
    """Normalize common whitespace/glyphs."""
    text = text.replace("\t", "    ")
    text = text.replace("\u00a0", " ")
    text = text.replace("\u2219", "•")
    return text


def ensure_fonts(pdf: FPDF) -> Tuple[str, str]:
    """
    Register Unicode body font (Noto) and mono font for code.
    Returns (body_font_family, mono_font_family).
    """
    body = "Helvetica"
    mono = "Courier"

    try:
        FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for style, (filename, url) in NOTO_FONTS.items():
            font_path = FONT_CACHE_DIR / filename
            if not font_path.exists() or font_path.stat().st_size < 1000:
                print(f"Downloading font {filename}...")
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    font_path.write_bytes(resp.read())
            pdf.add_font("Noto", style, str(font_path))
        body = "Noto"
    except Exception as e:
        print(
            "Warning: Could not load Unicode font (Noto Sans). "
            f"Falling back to Helvetica.\n  {e}"
        )

    # Core Courier is always available and avoids subset-table warnings.
    mono = "Courier"
    return body, mono


def parse_inline_segments(text: str) -> List[Tuple[str, str, str]]:
    """
    Parse inline markdown into segments:
      (text, style, kind)
    kind: "text" | "code" | "hashtag"
    style: "", "B", "I", "BI"
    """
    text = normalize_glyphs(text or "")
    if not text:
        return []

    # markdown links -> label
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    token_re = re.compile(
        r"("
        r"\*\*(.+?)\*\*|"  # bold **
        r"__(.+?)__|"  # bold __
        r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|"  # italic *
        r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)|"  # italic _
        r"`([^`]+)`|"  # inline code
        r"(?<![\w/])#([A-Za-z0-9_/-]+)"  # hashtag
        r")"
    )

    segments: List[Tuple[str, str, str]] = []
    pos = 0
    for m in token_re.finditer(text):
        if m.start() > pos:
            segments.append((text[pos : m.start()], "", "text"))
        if m.group(2) is not None:
            segments.append((m.group(2), "B", "text"))
        elif m.group(3) is not None:
            segments.append((m.group(3), "B", "text"))
        elif m.group(4) is not None:
            segments.append((m.group(4), "I", "text"))
        elif m.group(5) is not None:
            segments.append((m.group(5), "I", "text"))
        elif m.group(6) is not None:
            segments.append((m.group(6), "", "code"))
        elif m.group(7) is not None:
            segments.append((f"#{m.group(7)}", "I", "hashtag"))
        pos = m.end()
    if pos < len(text):
        segments.append((text[pos:], "", "text"))

    # merge adjacent identical
    merged: List[Tuple[str, str, str]] = []
    for t, s, k in segments:
        if not t:
            continue
        if merged and merged[-1][1] == s and merged[-1][2] == k:
            merged[-1] = (merged[-1][0] + t, s, k)
        else:
            merged.append((t, s, k))
    return merged


def combine_style(default_style: str, seg_style: str) -> str:
    has_b = "B" in default_style or "B" in seg_style
    has_i = "I" in default_style or "I" in seg_style
    if has_b and has_i:
        return "BI"
    if has_b:
        return "B"
    if has_i:
        return "I"
    return ""


def write_rich_line(
    pdf: FPDF,
    text: str,
    body_font: str,
    mono_font: str,
    size: int = 11,
    h: float = 6,
    indent: float = 0.0,
    default_style: str = "",
    bullet: bool = False,
    bullet_indent: float = 4.0,
) -> None:
    """Write a paragraph with mixed bold/italic/code/hashtag styles.

    Important: temporarily disables fpdf auto page-break so manual wrapping
    does not fight the engine and scatter one sentence across many pages.

    If bullet=True, draws a circular bullet on the first line only, using the
    same baseline/y as the text (avoids bullet/text splitting across lines).
    """
    segments = parse_inline_segments(text)
    if not segments and not bullet:
        return
    if not segments:
        segments = [("", "", "text")]

    left = pdf.l_margin + indent
    right = pdf.w - pdf.r_margin
    max_width = max(right - left, 10)

    # Disable auto page break while we manage wrapping ourselves
    prev_auto, prev_margin = pdf.auto_page_break, pdf.b_margin
    pdf.set_auto_page_break(False)

    def new_page_if_needed(y_pos: float) -> float:
        # Leave a little bottom room for the current line height
        if y_pos + h > pdf.h - prev_margin:
            pdf.add_page()
            return pdf.t_margin
        return y_pos

    x = left
    y = new_page_if_needed(pdf.get_y())
    pdf.set_xy(x, y)

    # Draw bullet AFTER final start y is known, so it stays with first text line
    if bullet:
        draw_bullet(pdf, y, indent=bullet_indent)

    def newline() -> None:
        nonlocal x, y
        y = new_page_if_needed(y + h)
        x = left
        pdf.set_xy(x, y)

    def put_text(part: str, font_name: str, font_style: str, kind: str) -> None:
        nonlocal x, y
        pdf.set_font(font_name, font_style, size)
        try:
            w = pdf.get_string_width(part)
        except Exception:
            part = re.sub(r"(\S{70})", r"\1 ", part)
            w = pdf.get_string_width(part)

        # Word/token wider than full line: hard-wrap by characters on same flow
        if w > max_width:
            buf = ""
            for ch in part:
                pdf.set_font(font_name, font_style, size)
                cw = pdf.get_string_width(buf + ch)
                if buf and cw > max_width:
                    bw = pdf.get_string_width(buf)
                    if x > left and (x - left) + bw > max_width + 0.01:
                        newline()
                    pdf.set_xy(x, y)
                    if kind == "code":
                        pdf.set_fill_color(240, 240, 240)
                        pdf.cell(bw, h, buf, fill=True)
                    else:
                        pdf.cell(bw, h, buf)
                    x += bw
                    buf = ch
                else:
                    buf += ch
            if buf:
                pdf.set_font(font_name, font_style, size)
                bw = pdf.get_string_width(buf)
                if x > left and (x - left) + bw > max_width + 0.01:
                    newline()
                pdf.set_xy(x, y)
                if kind == "code":
                    pdf.set_fill_color(240, 240, 240)
                    pdf.cell(bw, h, buf, fill=True)
                else:
                    pdf.cell(bw, h, buf)
                x += bw
            return

        # Normal wrap: if token doesn't fit remainder of line, go to next line once
        if x > left and (x - left) + w > max_width + 0.01:
            newline()
            pdf.set_font(font_name, font_style, size)

        pdf.set_xy(x, y)
        if kind == "code":
            pdf.set_fill_color(240, 240, 240)
            pdf.cell(w, h, part, fill=True)
        else:
            pdf.cell(w, h, part)
        x += w

    try:
        for raw_text, seg_style, kind in segments:
            style = combine_style(default_style, seg_style)
            font_name = mono_font if kind == "code" else body_font
            font_style = style if kind != "code" else (style if style in ("", "B") else "")

            # Split into words/spaces so wrapping happens on word boundaries
            parts = re.findall(r"\S+\s*|\s+", raw_text)
            for part in parts:
                if part:
                    put_text(part, font_name, font_style, kind)
    finally:
        # Advance to next line and restore auto page-break
        pdf.set_xy(pdf.l_margin, y + h)
        pdf.set_auto_page_break(prev_auto, prev_margin)


def draw_bullet(pdf: FPDF, y: float, indent: float = 5.0) -> None:
    """Draw a small filled circular black bullet."""
    r = 0.7
    cx = pdf.l_margin + indent + 1.6
    cy = y + 2.8
    pdf.set_fill_color(0, 0, 0)
    pdf.ellipse(cx - r, cy - r, 2 * r, 2 * r, style="F")


def is_heading(line: str) -> bool:
    return bool(re.match(r"^#{1,6}\s+\S", line))


def is_bullet(line: str) -> bool:
    return bool(re.match(r"^[\t ]*[-*+]\s+\S", line))


def is_numbered(line: str) -> bool:
    return bool(re.match(r"^[\t ]*\d+\.\s+\S", line))


def is_table_separator(line: str) -> bool:
    s = line.strip()
    if "|" not in s:
        return False
    # e.g. | --- | :---: | ---: |
    core = s.strip("|").strip()
    if not core:
        return False
    parts = [p.strip() for p in core.split("|")]
    return all(re.fullmatch(r":?-{3,}:?", p or "") for p in parts) and len(parts) >= 1


def is_table_row(line: str) -> bool:
    s = line.strip()
    return "|" in s and not is_table_separator(s)


def extract_table_block(lines: List[str], start: int) -> Tuple[Optional[List[List[str]]], int]:
    """
    If lines[start] begins a markdown table, return (rows, next_index).
    rows include header + body (separator discarded).
    """
    if start >= len(lines) or not is_table_row(lines[start]):
        return None, start
    # Need a separator on next non-empty? Standard GFM: header then separator.
    if start + 1 >= len(lines) or not is_table_separator(lines[start + 1]):
        return None, start

    def split_row(row: str) -> List[str]:
        s = row.strip().strip("|")
        return [c.strip() for c in s.split("|")]

    rows = [split_row(lines[start])]
    i = start + 2
    while i < len(lines) and is_table_row(lines[i]):
        rows.append(split_row(lines[i]))
        i += 1
    # normalize column count
    cols = max(len(r) for r in rows) if rows else 0
    rows = [r + [""] * (cols - len(r)) for r in rows]
    return rows, i


def strip_md_for_table_cell(text: str) -> str:
    text = normalize_glyphs(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text


def render_table_as_image(rows: List[List[str]], max_width_px: int = 1400) -> Path:
    """Render a markdown table to a temporary PNG image and return its path."""
    # Load fonts
    regular = None
    bold = None
    reg_path = FONT_CACHE_DIR / "NotoSans-Regular.ttf"
    bold_path = FONT_CACHE_DIR / "NotoSans-Bold.ttf"
    try:
        if reg_path.exists():
            regular = ImageFont.truetype(str(reg_path), 28)
        if bold_path.exists():
            bold = ImageFont.truetype(str(bold_path), 28)
    except Exception:
        pass
    if regular is None:
        regular = ImageFont.load_default()
    if bold is None:
        bold = regular

    clean = [[strip_md_for_table_cell(c) for c in row] for row in rows]
    cols = len(clean[0]) if clean else 0
    # Measure
    padding_x, padding_y = 16, 12
    col_widths = [0] * cols
    dummy = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(dummy)
    for r_i, row in enumerate(clean):
        font = bold if r_i == 0 else regular
        for c_i, cell in enumerate(row):
            bbox = draw.textbbox((0, 0), cell or " ", font=font)
            w = bbox[2] - bbox[0]
            col_widths[c_i] = max(col_widths[c_i], w + 2 * padding_x)

    # Cap total width
    total_w = sum(col_widths) + 2
    if total_w > max_width_px and total_w > 0:
        scale = max_width_px / total_w
        col_widths = [max(int(w * scale), 40) for w in col_widths]
        total_w = sum(col_widths) + 2

    # Row heights (simple single-line)
    row_h = 28 + 2 * padding_y
    total_h = row_h * len(clean) + 2

    img = Image.new("RGB", (total_w, total_h), "white")
    draw = ImageDraw.Draw(img)

    # Header background
    draw.rectangle([0, 0, total_w - 1, row_h], fill=(240, 240, 240))

    # Grid + text
    y = 0
    for r_i, row in enumerate(clean):
        x = 0
        font = bold if r_i == 0 else regular
        for c_i, cell in enumerate(row):
            w = col_widths[c_i]
            draw.rectangle([x, y, x + w, y + row_h], outline=(180, 180, 180), width=1)
            # clip text roughly by available width
            text = cell
            while text and (draw.textbbox((0, 0), text, font=font)[2] > w - 2 * padding_x):
                text = text[:-1]
            if text != cell and text:
                text = text[:-1] + "…"
            draw.text((x + padding_x, y + padding_y), text, fill="black", font=font)
            x += w
        y += row_h

    # Outer border
    draw.rectangle([0, 0, total_w - 1, total_h - 1], outline=(120, 120, 120), width=2)

    tmp = tempfile.NamedTemporaryFile(prefix="obs_table_", suffix=".png", delete=False)
    img.save(tmp.name, format="PNG")
    tmp.close()
    return Path(tmp.name)


def write_code_block(
    pdf: FPDF, code_lines: List[str], mono_font: str, body_font: str
) -> None:
    """Render a fenced code block with mono font and light background."""
    if not code_lines:
        return
    pdf.ln(1)
    pdf.set_font(mono_font, "", 9)
    line_h = 5
    # background block
    block_text_height = line_h * len(code_lines) + 4
    # page-break if needed
    if pdf.get_y() + block_text_height > pdf.h - pdf.b_margin:
        pdf.add_page()

    x0 = pdf.l_margin
    y0 = pdf.get_y()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_fill_color(245, 245, 245)
    pdf.set_draw_color(210, 210, 210)
    pdf.rect(x0, y0, width, block_text_height, style="DF")

    pdf.set_xy(x0 + 2, y0 + 2)
    for line in code_lines:
        # keep leading spaces for code indentation
        safe = line.replace("\t", "    ")
        pdf.set_x(x0 + 2)
        try:
            pdf.cell(width - 4, line_h, safe)
        except Exception:
            pdf.cell(width - 4, line_h, re.sub(r"(\S{80})", r"\1 ", safe))
        pdf.ln(line_h)
    pdf.set_y(y0 + block_text_height + 2)
    pdf.set_font(body_font, "", 11)


def render_to_pdf(
    pdf: FPDF,
    title: str,
    content: str,
    current_dir: Path,
    vault_root: Path,
    body_font: str = "Helvetica",
    mono_font: str = "Courier",
) -> int:
    """Render one note. Returns number of images/tables embedded."""
    images_added = 0
    temp_files: List[Path] = []

    # Margins are set once in create_pdf; keep x at left content edge
    pdf.set_x(pdf.l_margin)

    # Note title
    write_rich_line(pdf, title, body_font, mono_font, size=14, h=8, default_style="B")
    pdf.ln(2)

    content = preprocess_content(content, current_dir, vault_root)
    content = extract_callouts(content)

    # Keep blank lines exactly as authored (splitlines keeps structure)
    lines = content.splitlines()
    i = 0
    paragraph_parts: List[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_parts
        if paragraph_parts:
            write_rich_line(
                pdf,
                " ".join(paragraph_parts),
                body_font,
                mono_font,
                size=11,
                h=6,
            )
            paragraph_parts = []

    try:
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Fenced code block ``` or ```
            fence = re.match(r"^```(\w+)?\s*$", stripped)
            if fence:
                flush_paragraph()
                i += 1
                code_lines: List[str] = []
                while i < len(lines) and not re.match(r"^```\s*$", lines[i].strip()):
                    code_lines.append(lines[i].rstrip("\n"))
                    i += 1
                if i < len(lines):
                    i += 1  # closing fence
                write_code_block(pdf, code_lines, mono_font, body_font)
                continue

            # Image marker
            img_match = re.match(r"<<OBS_IMAGE:(.+)>>", stripped)
            if img_match:
                flush_paragraph()
                embed_target = img_match.group(1)
                img_path = resolve_attachment_path(embed_target, current_dir, vault_root)
                if img_path and img_path.exists():
                    try:
                        with Image.open(img_path) as im:
                            orig_w, orig_h = im.size
                        max_w = 160
                        aspect = orig_h / orig_w if orig_w > 0 else 1
                        display_w = min(max_w, max(orig_w * 0.26, 40))
                        available = pdf.h - pdf.get_y() - pdf.b_margin - 10
                        if display_w * aspect > available and available > 30:
                            display_w = available / aspect
                        x = (pdf.w - display_w) / 2
                        pdf.image(str(img_path), x=x, w=display_w)
                        pdf.ln(4)
                        images_added += 1
                    except (UnidentifiedImageError, OSError, Exception):
                        write_rich_line(
                            pdf,
                            f"[Could not load image: {embed_target}]",
                            body_font,
                            mono_font,
                            size=9,
                            h=5,
                            default_style="I",
                        )
                else:
                    write_rich_line(
                        pdf,
                        f"[Image not found: {embed_target}]",
                        body_font,
                        mono_font,
                        size=9,
                        h=5,
                        default_style="I",
                    )
                i += 1
                continue

            # Markdown table -> image
            table_rows, next_i = extract_table_block(lines, i)
            if table_rows is not None:
                flush_paragraph()
                try:
                    table_img = render_table_as_image(table_rows)
                    temp_files.append(table_img)
                    with Image.open(table_img) as im:
                        tw, th = im.size
                    max_w = pdf.w - pdf.l_margin - pdf.r_margin
                    # convert px->mm roughly (96dpi)
                    display_w = min(max_w, tw * 0.26)
                    available = pdf.h - pdf.get_y() - pdf.b_margin - 10
                    aspect = th / tw if tw else 1
                    if display_w * aspect > available and available > 40:
                        display_w = available / aspect
                    x = pdf.l_margin + (max_w - display_w) / 2
                    pdf.image(str(table_img), x=x, w=display_w)
                    pdf.ln(4)
                    images_added += 1
                except Exception as e:
                    write_rich_line(
                        pdf,
                        f"[Could not render table: {e}]",
                        body_font,
                        mono_font,
                        size=9,
                        h=5,
                        default_style="I",
                    )
                i = next_i
                continue

            # Headings (# Title only)
            if is_heading(stripped):
                flush_paragraph()
                level = len(stripped) - len(stripped.lstrip("#"))
                heading_text = stripped[level:].strip()
                if level <= 1:
                    write_rich_line(
                        pdf, heading_text, body_font, mono_font, size=13, h=7, default_style="B"
                    )
                    pdf.ln(2)
                elif level == 2:
                    write_rich_line(
                        pdf, heading_text, body_font, mono_font, size=12, h=7, default_style="B"
                    )
                    pdf.ln(1)
                else:
                    write_rich_line(
                        pdf, heading_text, body_font, mono_font, size=11, h=6, default_style="B"
                    )
                    pdf.ln(1)
                i += 1
                continue

            # Horizontal rule
            if re.match(r"^---+$", stripped):
                flush_paragraph()
                pdf.ln(2)
                y = pdf.get_y()
                pdf.set_draw_color(180, 180, 180)
                pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
                pdf.ln(3)
                i += 1
                continue

            # Bullet list with circular mark (drawn on same baseline as first text line)
            if is_bullet(line):
                flush_paragraph()
                item = re.sub(r"^[\t ]*[-*+]\s+", "", line)
                write_rich_line(
                    pdf,
                    item,
                    body_font,
                    mono_font,
                    size=11,
                    h=6,
                    indent=10.0,
                    bullet=True,
                    bullet_indent=4.0,
                )
                i += 1
                continue

            # Numbered list
            if is_numbered(line):
                flush_paragraph()
                m = re.match(r"^[\t ]*(\d+)\.\s+(.*)$", line)
                if m:
                    num, item = m.group(1), m.group(2)
                    write_rich_line(
                        pdf,
                        f"{num}. {item}",
                        body_font,
                        mono_font,
                        size=11,
                        h=6,
                        indent=5.0,
                    )
                else:
                    write_rich_line(
                        pdf, stripped, body_font, mono_font, size=11, h=6, indent=5.0
                    )
                i += 1
                continue

            # Blank line: preserve spacing from markdown
            if not stripped:
                flush_paragraph()
                pdf.ln(4)
                i += 1
                continue

            # Regular paragraph text
            paragraph_parts.append(stripped)
            i += 1

        flush_paragraph()
        pdf.ln(3)
    finally:
        for p in temp_files:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass

    return images_added


def create_pdf(input_folder: Path, output_path: Path) -> None:
    """Main conversion routine."""
    print(f"Scanning folder: {input_folder}")
    md_files = find_markdown_files(input_folder)

    if not md_files:
        print("No markdown files found.")
        sys.exit(1)

    print(f"Found {len(md_files)} markdown file(s)")

    vault_root = input_folder

    notes = []
    for md_path in md_files:
        try:
            raw = md_path.read_text(encoding="utf-8", errors="replace")
            frontmatter_data, content = parse_frontmatter(raw)
            title = get_title(frontmatter_data, md_path)
            # Do NOT strip blank lines from content; only trim file ends lightly
            content = content.lstrip("\n").rstrip()
            notes.append((title, content, md_path, md_path.parent))
        except Exception as e:
            print(f"  Warning: Could not read {md_path.name}: {e}")

    if not notes:
        print("No readable notes found.")
        sys.exit(1)

    pdf = FPDF()
    # Bigger page margins for readability
    pdf.set_left_margin(22)
    pdf.set_right_margin(22)
    pdf.set_top_margin(20)
    pdf.set_auto_page_break(auto=True, margin=20)
    body_font, mono_font = ensure_fonts(pdf)

    # First page: Contents only (no folder title, no minus signs)
    pdf.add_page()
    pdf.set_font(body_font, "B", 16)
    pdf.cell(0, 10, "Contents", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    pdf.set_font(body_font, "", 11)
    for title, _, _, _ in notes:
        pdf.cell(0, 7, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Notes
    total_images = 0
    for idx, (title, content, md_path, md_dir) in enumerate(notes, 1):
        print(f"[{idx}/{len(notes)}] {title}")
        pdf.add_page()
        images = render_to_pdf(
            pdf, title, content, md_dir, vault_root, body_font, mono_font
        )
        total_images += images

    try:
        pdf.output(str(output_path))
        print(f"\n✓ Created: {output_path}")
        print(f"  Pages: ~{pdf.page_no()}")
        print(f"  Images/tables embedded: {total_images}")
    except Exception as e:
        print(f"Error writing PDF: {e}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a folder of Obsidian Markdown files to a single PDF."
    )
    parser.add_argument(
        "folder",
        help="Path to the folder containing Obsidian .md files (processed recursively)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional output PDF path (default: <folder-name>.pdf in current directory)",
    )
    args = parser.parse_args()

    input_path = Path(args.folder).expanduser().resolve()
    if not input_path.exists():
        print(f"Error: Folder does not exist: {input_path}")
        sys.exit(1)
    if not input_path.is_dir():
        print(f"Error: Not a directory: {input_path}")
        sys.exit(1)

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        output_path = Path.cwd() / f"{input_path.name}.pdf"

    create_pdf(input_path, output_path)


if __name__ == "__main__":
    main()
