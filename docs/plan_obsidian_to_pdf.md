# Obsidian → PDF Converter — Implementation Plan

This document records the design, decisions, bugs fixed, and verification steps for
`obsidian_to_pdf`, a Python CLI that converts a folder of Obsidian Markdown notes into
a single clean PDF.

---

## 1. Goal

Build a simple, non-interactive CLI tool that:

- Takes a folder of Obsidian `.md` notes
- Recursively finds all markdown files
- Produces one readable PDF
- Defaults the output filename to the folder name
- Handles common Obsidian syntax without cloning the Obsidian UI theme

### Primary use case

Export study/vault folders (e.g. Kubernetes notes) into a portable PDF for reading,
printing, or sharing.

---

## 2. Constraints & Preferences

| Constraint | Choice |
|---|---|
| Interface | Simple CLI only (no interactive menu) |
| Scope | Entire folder, recursive |
| Default output name | `<folder-name>.pdf` |
| Styling | Clean/readable, not Obsidian theme clone |
| Attachments | Must resolve Obsidian default `Attachments/` folders |
| Dependencies | Prefer pure-Python; run via `uv run` |
| Obsidian syntax | Wikilinks, embeds, callouts, frontmatter |
| Runtime | Works on macOS; resilient to Unicode content |

---

## 3. Tech Stack

| Component | Library / approach | Why |
|---|---|---|
| PDF engine | `fpdf2` | Pure Python, good control over layout |
| Images / tables | `Pillow` | Load embeds; render markdown tables as PNG |
| Frontmatter | Manual parse + `PyYAML` | Avoid `python-frontmatter` Py3.9 issues |
| Body fonts | Noto Sans (downloaded once) | Unicode coverage (Greek, symbols, etc.) |
| Code font | Core PDF `Courier` | Avoid TTF subset warnings (`bdat`/`bloc`) |
| Runner | `uv run python3 ...` | Simple local dependency management |

### Font cache

```
~/.cache/obsidian_to_pdf_fonts/
  NotoSans-Regular.ttf
  NotoSans-Bold.ttf
  NotoSans-Italic.ttf
  NotoSans-BoldItalic.ttf
```

Fonts are downloaded on first run from the official Noto fonts repository and reused afterward.

---

## 4. Project Layout

```
obsidian_to_pdf/
  obsidian_to_pdf.py      # Main CLI + renderer
  requirements.txt        # fpdf2, Pillow, PyYAML
  IMPLEMENTATION_PLAN.md  # This document
```

Root project: `/Users/nikk/GitHubProjects/personal_utilities`

---

## 5. Architecture & Data Flow

```
Input folder
    │
    ▼
find_markdown_files()          # recursive *.md, sorted
    │
    ▼
For each note:
  parse_frontmatter()          # YAML header → metadata + body
  get_title()                  # frontmatter title or filename stem
    │
    ▼
create_pdf()
  ensure_fonts()               # Noto body + Courier mono
  page 1: Contents only
  for each note:
      add_page()
      render_to_pdf()
         preprocess_content()  # embeds → markers, then wikilinks
         extract_callouts()
         line-by-line render:
            code fences, images, tables, headings,
            HR, bullets, numbered lists, blanks, paragraphs
    │
    ▼
pdf.output(output_path)
```

### Key helpers

| Helper | Role |
|---|---|
| `parse_frontmatter` | Split YAML header from body |
| `find_markdown_files` | Recursive `.md` discovery |
| `get_title` | Title from frontmatter or filename |
| `convert_wikilinks` | `[[Note\|Alias]]` → plain text |
| `convert_obsidian_embeds` | `![[img]]` → `<<OBS_IMAGE:...>>` marker |
| `resolve_attachment_path` | Find files under note dir / Attachments / vault |
| `extract_callouts` | `> [!note]` → bold label + body |
| `parse_inline_segments` | Bold, italic, inline code, hashtags |
| `write_rich_line` | Mixed-style paragraph writer with safe wrapping |
| `draw_bullet` | Small filled circular bullet |
| `extract_table_block` | Detect GFM markdown tables |
| `render_table_as_image` | Table → temporary PNG via Pillow |
| `write_code_block` | Fenced code with mono + background |
| `render_to_pdf` | One-note renderer |
| `create_pdf` | Orchestration + TOC + output |
| `main` | Argparse CLI |

---

## 6. Feature Implementation Plan

### 6.1 CLI

```bash
uv run python3 obsidian_to_pdf/obsidian_to_pdf.py <folder> [-o output.pdf]
```

- `folder` (required): vault/subfolder path
- `-o/--output` (optional): explicit PDF path
- Default output: `./<folder-name>.pdf`

### 6.2 Note discovery & metadata

1. Recursively collect `*.md` files, sorted by relative path
2. Parse optional YAML frontmatter between `---` fences
3. Title priority: `title` / `Title` frontmatter → filename stem
4. Preserve internal blank lines in body content (do not collapse the file)

### 6.3 First page: Contents only

Requirements:

- No folder title
- No decorative minus signs / bullets in TOC
- Plain list of note titles
- No cover page branding

Implementation:

- `pdf.add_page()`
- Bold heading: `Contents`
- One line per note title

### 6.4 Page geometry

| Setting | Value | Rationale |
|---|---|---|
| Left/right margin | 22 mm | More readable whitespace |
| Top margin | 20 mm | Breathing room |
| Bottom / auto page-break | 20 mm | Avoid clipping near edge |

### 6.5 Block-level Markdown

| Markdown | PDF behavior |
|---|---|
| `#`–`######` headings | Bold; size by level. Heading requires space after `#` (`# Title`) so `#tag` is not a heading |
| Blank lines | Preserve vertical spacing (`pdf.ln(4)`) |
| `-` / `*` / `+` lists | Small circular black bullet + indented rich text |
| `1. item` lists | Keep original numbers (`1. item`) |
| `---` horizontal rule | Light gray full-width line |
| Fenced code ` ``` ` | Mono block, light gray background, bordered |
| Inline `` `code` `` | Mono + light gray fill |
| GFM tables | Rendered as PNG image and embedded |
| Images `![[...]]` / resolved paths | Centered, width-capped, aspect preserved |
| Callouts `> [!type]` | `**Type:** title` + unquoted body lines |

### 6.6 Inline Markdown

Handled by `parse_inline_segments` → `write_rich_line`:

| Syntax | Style |
|---|---|
| `**bold**` / `__bold__` | Bold |
| `*italic*` / `_italic_` | Italic |
| `` `code` `` | Mono + gray background |
| `#tag` | Italic hashtag (not a heading) |
| `[label](url)` | Label only (URL dropped) |

Segments are merged when adjacent style/kind match, then word-wrapped.

### 6.7 Obsidian-specific preprocessing

Order is critical:

1. **Embeds first** — `![[target]]` / `![[target|alias]]`
   - Image extensions → `<<OBS_IMAGE:target>>`
   - Non-image embeds → alias or target text
2. **Wikilinks second** — `[[Note]]` / `[[Note|Alias]]` → display text  
   Doing wikilinks first would strip the `![[...]]` image marker incorrectly.

Attachment resolution candidates:

1. Relative to current note directory
2. `current_dir/Attachments/`
3. `parent/Attachments/`
4. `vault_root/Attachments/`
5. `vault_root/<path>`
6. Any `Attachments/` folder under the vault (by filename)

### 6.8 Tables as images

Motivation: fpdf2 native tables are awkward for mixed markdown; image rendering is
reliable and matches “tables look like tables” expectation.

Steps:

1. Detect header row + separator (`| --- | --- |`)
2. Collect following body rows
3. Strip light markdown from cells
4. Measure with Noto fonts via Pillow
5. Draw header background, grid, text
6. Save temp PNG, embed with `pdf.image`, delete temp file

### 6.9 Circular bullets

- Small filled ellipse (`r ≈ 0.7`)
- Drawn on the **same baseline/y** as the first text line of the item
- Implemented inside `write_rich_line(..., bullet=True)` so page-break adjustments
  cannot leave the bullet on a previous line while text moves

---

## 7. Critical Layout Engine: `write_rich_line`

This is the most delicate part of the renderer.

### Problem history

1. Long mixed-style paragraphs (especially with inline code) could scatter across
   many pages when fpdf auto page-break fought manual `set_xy` tracking.
2. Drawing a bullet *before* calling `write_rich_line` could leave the bullet on a
   different line than the sentence if `y` was adjusted inside the writer.

### Solution

1. Temporarily **disable auto page-break** while writing a rich paragraph
2. Track `x`/`y` manually
3. Wrap on word boundaries; hard-wrap only when a single token exceeds full line width
4. Page-break only when `y + line_height` exceeds bottom margin
5. Restore previous auto page-break settings in `finally`
6. If `bullet=True`, draw the circle **after** the final start `y` is known

### Pseudocode

```
disable auto page break
y = maybe_new_page(current_y)
if bullet: draw_bullet(y)
for each styled token/word:
    if doesn't fit remaining width: newline (maybe page break)
    draw token at (x, y); advance x
move cursor to (left_margin, y + h)
restore auto page break
```

---

## 8. Bugs Found & Fixed

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | `![[image]]` became plain text / broken | Wikilinks ran before embeds | Process embeds first; use `<<OBS_IMAGE:...>>` marker |
| 2 | Image marker stripped by wikilink regex | Marker looked link-like / order bug | Dedicated marker + embed-first pipeline |
| 3 | Crash on Greek chars (e.g. `009Β_...`) | Helvetica lacks Unicode glyphs | Download/cache Noto Sans family |
| 4 | `Not enough horizontal space...` | Unsafe `set_x` / long unwrapped runs | Safe rich-text writer with width checks |
| 5 | Numbered lists looked like bullets | Ordered items forced through bullet path | Separate `is_numbered` path; keep `N. text` |
| 6 | Bold not styled | `**...**` stripped or ignored | Inline segment parser + style application |
| 7 | Hashtags treated as headings | `#tag` matched heading regex | Heading requires `#` + whitespace + non-space |
| 8 | First page had title / minus signs | Cover + dashed TOC | Contents-only page with plain titles |
| 9 | Blank lines collapsed | Body whitespace stripped/ignored | Preserve blank lines as vertical space |
| 10 | Bullets were `-` characters | Text bullet prefix | Draw filled circular ellipse |
| 11 | Code looked like body text | No mono / fence handling | Inline code + fenced code blocks |
| 12 | Tables unreadable / missing | No table support | Detect GFM tables → PNG embed |
| 13 | Long sentence in `006B_StatefulSets` exploded across pages | Auto page-break vs manual wrap race | Disable auto-break inside `write_rich_line` |
| 14 | Bullet on different line than sentence | Bullet drawn before writer adjusted `y` | Draw bullet inside writer on final start `y` |
| 15 | `bdat`/`bloc` subset warnings on run | Custom TTF/TTC mono font subsetting | Use core `Courier`; quiet fontTools loggers |

---

## 9. Rendering Rules (Current Spec)

### Typography

- Body: Noto Sans 11 pt
- Note title: Bold 14 pt
- H1: Bold 13 pt
- H2: Bold 12 pt
- H3+: Bold 11 pt
- Code: Courier 9–11 pt on light gray

### Lists

- Unordered: small black circle + text indent ~10 mm
- Ordered: `N. item` with modest indent
- Nested depth: currently shallow (same indent levels); deeper nesting is future work

### Spacing

- Blank markdown line → ~4 mm gap
- After note title → small gap
- After headings → 1–2 mm gap
- After images/tables → ~4 mm gap

### Images

- Max display width ~160 mm (capped by content width)
- Centered
- Shrink further if not enough vertical room on current page
- Missing/unloadable images → italic placeholder text

---

## 10. Verification Plan

### Compile check

```bash
cd /Users/nikk/GitHubProjects/personal_utilities
python3 -m py_compile obsidian_to_pdf/obsidian_to_pdf.py
```

### Full vault conversion (primary regression target)

```bash
uv run python3 obsidian_to_pdf/obsidian_to_pdf.py \
  "/Users/nikk/Obsidian/Data Engineering/02_Cloud Services/03_Kubernetes" \
  -o /tmp/03_Kubernetes.pdf
```

**Expected:**

- No font subset warnings (`bdat`/`bloc`/etc.)
- ~20 notes converted
- ~26 pages (order of magnitude; content-dependent)
- At least 1 table image (from `012A_kubectl & kubeconfig`)
- Clean exit and PDF written

### Focus notes to eyeball in the PDF

| Note | What to check |
|---|---|
| Contents page | Titles only; no minus signs; no folder header |
| `003_The Declarative Model` | Numbered lists, bold, hashtags |
| `006B_StatefulSets` | Long paragraph with inline code stays continuous; bullets aligned with first text line |
| `012A_kubectl & kubeconfig` | Markdown table rendered as image |
| Any note with fences | Code blocks mono + gray background |
| Notes with `![[...]]` | Images resolved from Attachments |

### Single-note smoke test (optional)

Copy one markdown file into a temp folder and run the converter to isolate layout bugs
without rendering the full vault.

---

## 11. Implementation Timeline (What Was Done)

1. **Scaffold CLI**
   - Argparse, recursive scan, default output name, requirements file

2. **Baseline PDF pipeline**
   - Frontmatter, titles, multi-page notes, basic text output

3. **Obsidian syntax**
   - Wikilinks, embeds, attachment resolution, callouts

4. **Unicode & robustness**
   - Noto font cache; safer layout writer

5. **Typography pass**
   - Bold/italic/hashtags; numbered vs bullet lists

6. **Presentation pass (user-requested)**
   - TOC-only first page
   - Preserve blank lines
   - Circular bullets
   - Inline + fenced code styling
   - Tables as images

7. **Layout bugfix pass**
   - Larger margins
   - Smaller bullets
   - Fix page-scatter on long rich paragraphs (`StatefulSets`)
   - Fix bullet/text baseline split
   - Eliminate mono-font subset warnings

---

## 12. Known Limitations / Future Work

| Item | Notes |
|---|---|
| Page-numbered TOC with links | Currently plain title list; could add destinations + page numbers |
| Deep nested lists | Indent levels are basic; nested bullets could step further |
| Blockquotes (non-callout) | Partially handled via callout path; plain `>` quotes could be styled |
| Math / Mermaid / advanced embeds | Not supported |
| SVG embeds | May fail depending on Pillow/SVG support; raster formats preferred |
| True multi-line table cells | Table renderer is single-line-per-cell with ellipsis clipping |
| Packaging polish | Optional `pyproject.toml`, console script entry point |
| Root README | Document the tool at repo root if desired |
| Theme options | Light customization flags (font size, margins) via CLI |

---

## 13. Dependency Notes

`requirements.txt` (conceptually):

```
fpdf2
Pillow
PyYAML
```

Install/run:

```bash
cd /Users/nikk/GitHubProjects/personal_utilities
uv run python3 obsidian_to_pdf/obsidian_to_pdf.py <folder> -o <out.pdf>
```

---

## 14. Design Principles (Keep These)

1. **Deterministic order** — sorted file paths; stable TOC
2. **Obsidian-first preprocessing** — embeds before wikilinks
3. **Manual control of wrapping** — don’t let auto page-break fight custom rich text
4. **Same-baseline decorations** — bullets/ornaments drawn with final text `y`
5. **Graceful degradation** — missing images/fonts produce warnings/placeholders, not hard crashes when avoidable
6. **Readable over faithful** — clean study PDF, not a 1:1 Obsidian clone
7. **Quiet CLI** — no noisy font toolchain warnings in normal successful runs

---

## 15. Quick Reference — Important Paths

| Path | Purpose |
|---|---|
| `obsidian_to_pdf/obsidian_to_pdf.py` | Main script |
| `obsidian_to_pdf/requirements.txt` | Dependencies |
| `obsidian_to_pdf/IMPLEMENTATION_PLAN.md` | This plan |
| `~/.cache/obsidian_to_pdf_fonts/` | Cached Noto fonts |
| Test vault | `/Users/nikk/Obsidian/Data Engineering/02_Cloud Services/03_Kubernetes` |
| Latest test output | `/tmp/03_Kubernetes.pdf` |

---

## 16. Acceptance Checklist

- [x] Recursive folder conversion
- [x] Default PDF name from folder name
- [x] Frontmatter title support
- [x] Wikilinks → readable text
- [x] Image embeds via Attachments resolution
- [x] Callouts readable
- [x] Contents-only first page (no title, no minus signs)
- [x] Blank lines preserved
- [x] Circular black bullets (small)
- [x] Bold / italic / hashtags
- [x] Inline + fenced code as code
- [x] Numbered lists keep numbers
- [x] Tables rendered as images
- [x] Comfortable page margins
- [x] No multi-page scatter on long inline-code sentences
- [x] Bullet stays on same line as list text
- [x] No `bdat`/`bloc` font subset warnings on normal runs
- [x] Kubernetes vault converts successfully end-to-end
