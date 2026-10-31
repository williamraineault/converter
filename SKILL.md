---
name: converter
description: Convert any file to another format (images, video, audio, 3d models, documents, ebooks, archives, fonts, data, subtitles). Use whenever a user asks to convert, export, save as, or turn a file into another format, or when a later step needs a file in a different format. One command, JSON output, tells you what is possible on this machine and what to install if something is missing.
---

# converter

`convert.py` sits next to this file. Always pass `--json`.

```
python3 convert.py --can FILE --json            # every format FILE can become here, by category
python3 convert.py --can FILE OUT --json        # will it work: tool, exact command, missing tools
python3 convert.py FILE OUT --json              # do it (add -f to overwrite OUT)
python3 convert.py FILE... --to EXT --json      # batch: output written next to each input
python3 convert.py --doctor --json              # installed tools and install commands
python3 convert.py --list [CATEGORY] --json     # all known extensions
```

Result lines: `{"ok": true, "input", "output", "backend"}` or
`{"ok": false, "input", "output", "error", "missing": [{"backend", "install"}]}`.
Exit codes: 0 ok, 1 the tool failed, 2 unsupported or tool not installed, 3 bad arguments.

Rules of thumb:
- Format is taken from the extension, so name the output file with the extension you want.
- If `ok` is false and `missing` is non-empty, run the `install` command and retry.
- Raster to SVG is tracing (black and white outline); it needs potrace.
- `.rar` can be read, never written. DRM-protected files are not supported.
- Nothing is overwritten without `-f`.
