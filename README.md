# converter

One command that turns a file into another format. One Python file, no dependencies,
built so an AI agent can use it without being told how.

```
python3 convert.py photo.heic photo.jpg
python3 convert.py talk.mkv --to mp3
python3 convert.py model.fbx model.glb
python3 convert.py --can model.fbx          # what can this file become on this machine?
```

It is a router, not a codec library. Each job goes to the first installed tool that can do
it (ImageMagick, ffmpeg, pandoc, LibreOffice, Calibre, Assimp, Blender, FontForge, potrace,
7-Zip, or the macOS built-ins `sips` and `textutil`); if that tool fails the next capable
one is tried. Archives and data files are handled natively. 424 extensions in 10 categories
are known (`formats/`).

## Install

No git needed:

```
curl -sL https://github.com/williamraineault/converter/archive/main.tar.gz | tar xz
python3 converter-main/convert.py --doctor
```

Needs Python 3.8 or newer (reading `.toml` needs 3.11). `--doctor` lists the tools present and a one-line install for each missing one. On a Mac,
images and text documents work with nothing installed.

To make agents reach for it on their own, drop the folder into a skills directory
(for Claude Code: `~/.claude/skills/converter`). `SKILL.md` is the trigger.

## Usage

```
convert.py INPUT OUTPUT            explicit output path
convert.py INPUT... --to EXT       one or more inputs, output written next to each
convert.py --can INPUT             every format INPUT can become here, by category
convert.py --can INPUT OUTPUT      plan only: tool, exact command, and tools that could also do it
convert.py --list [CATEGORY]       categories, or one category's extensions
convert.py --doctor                which tools are installed
  -f, --force                      overwrite an existing output
  --json                           machine-readable output
```

Exit codes: `0` ok, `1` conversion failed, `2` unsupported (unknown extension, no tool
handles that pair, or the tool isn't installed), `3` bad arguments.

## For agents

```
python3 convert.py --can in.ext --json          # {"input": ..., "outputs": {"images": ["jpg", ...], ...}}
python3 convert.py --can in.ext out.ext --json  # {"ok", "backend", "backends", "command", "missing"}
python3 convert.py in.ext out.ext --json        # {"ok": true, "input", "output", "backend"}
```

A failure is `{"ok": false, "input", "output", "error", "missing": [{"backend", "install"}]}`.
If `missing` is non-empty, running one of those install commands and retrying will work.
Nothing is overwritten without `-f`. Formats are inferred from extensions only;
`.tar.gz`, `.tar.bz2` and `.tar.xz` are recognised as one unit.

## Tools

| tool | handles | install |
|---|---|---|
| ImageMagick | images, image ↔ pdf | `brew install imagemagick` |
| ffmpeg | video, audio, video ↔ gif/png/webp, subtitles | `brew install ffmpeg` |
| potrace | raster → svg (traced outline) | `brew install potrace` |
| pandoc | markdown / html / docx / odt / rst / tex / epub | `brew install pandoc` |
| LibreOffice | office documents, anything → pdf | `brew install --cask libreoffice` |
| Calibre | ebooks | `brew install --cask calibre` |
| Assimp, Blender | 3d meshes | `brew install assimp`, `brew install --cask blender` |
| FontForge | fonts | `brew install fontforge` |
| 7-Zip | 7z, rar (read only), iso, cab, … | `brew install sevenzip` |
| built in | zip / tar / tgz / tbz2 / txz, json / jsonl / csv / tsv / plist / toml | — |

## Layout

```
convert.py        the whole tool
SKILL.md          agent instructions (Agent Skills format)
formats/*.txt     one category per file, one extension per line, alphabetical
```

`formats/README.md` explains what was included and why. To add a format, add its
extension to the right list; to add a tool, add one `Backend(...)` line to the registry
in `convert.py`.
