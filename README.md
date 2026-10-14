# Personal Utilities
Utilities that I have built and use for personal tasks:

- **simple_disk_sync**. A tool to sync the files of an external hard disk with my Desktop folders.
- **obsidian_to_pdf**. Converts a folder of Obsidian Markdown notes into a single PDF file. 

## Setup
From the repo root run:

```bash
uv sync
```

Python is required.

## How to run

### simple_disk_sync
Execute (with no command-line arguments):

```bash
uv run python src/simple_disk_sync.py
```

 It asks for 2 folders: the *Internal* (in Desktop) and the *External* (for the external disk). It then prints a difference report and offers a menu:

1. Sync internal → external (copy new/newer files and delete files that exist only on external)
2. Sync external → internal (copy new/newer files and delete files that exist only on internal)
3. Merge internal → external (copy new/newer files, no deletion)
4. Merge external → internal (copy new/newer files, no deletion)

Press Enter at the menu to quit. Files that exist only in the target are left alone unless you pick a sync option (1 or 2).

Default folders and excluded folders are hardcoded near the bottom of [src/simple_disk_sync.py](src/simple_disk_sync.py). Change those before running, or type other paths when prompted. Press Enter at a path prompt to keep the default. The script exits if either folder does not exist.

### obsidian_to_pdf
Execute any of the following:

```bash
uv run python src/obsidian_to_pdf.py /path/to/notes
uv run python src/obsidian_to_pdf.py /path/to/notes -o /path/to/output.pdf
```

`folder` is required. `-o` / `--output` is optional. 

It walks the folder recursively. The default output is `<folder-name>.pdf` in the current directory. Wikilinks, embeds, and images under Obsidian `Attachments/` folders are resolved. On first run it downloads Noto Sans into `~/.cache/obsidian_to_pdf_fonts/`.
