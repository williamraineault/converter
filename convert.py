#!/usr/bin/env python3
"""convert.py - turn a file into another format with one command.

  convert.py photo.heic photo.jpg         explicit output
  convert.py talk.mkv clip.mov --to mp3   one or more inputs, output written next to each
  convert.py --can model.fbx              every format this file can become on this machine
  convert.py --can model.fbx model.glb    plan only: which tool would run, and the command
  convert.py --list [images]              known extensions (read from formats/*.txt)
  convert.py --doctor                     which tools are installed

No dependencies. Each job goes to the first installed tool that handles it
(ImageMagick, ffmpeg, pandoc, LibreOffice, Calibre, Assimp, Blender, FontForge,
7-Zip, or the macOS built-ins sips and textutil); archives and data files are
handled natively. If a tool fails, the next capable one is tried.
--json prints one JSON object per job. Exit: 0 ok, 1 failed, 2 unsupported, 3 usage.
"""
import argparse, collections, csv, io, json, os, plistlib, shlex, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FORMATS = {}  # category -> set of extensions
if not os.path.isdir(os.path.join(HERE, "formats")):
    sys.exit("convert.py needs the formats/ folder next to it; download the whole repo")
for name in sorted(os.listdir(os.path.join(HERE, "formats"))):
    if name.endswith(".txt"):
        with open(os.path.join(HERE, "formats", name)) as f:
            FORMATS[name[:-4]] = {line.strip().lstrip(".") for line in f if line.strip()}

TARBALLS = {".tar.gz": "tgz", ".tar.bz2": "tbz2", ".tar.xz": "txz"}


def ext(path):
    low = path.lower()
    for suffix, e in TARBALLS.items():
        if low.endswith(suffix):
            return e
    return os.path.splitext(low)[1][1:]


def stem(path):
    e = ext(path)
    return path[: -len(e) - 1] if e else path


def cats(e):
    return [c for c, exts in FORMATS.items() if e in exts]


class Failed(Exception):
    def __init__(self, msg, missing=()):
        super().__init__(msg)
        self.missing = [{"backend": b.name, "install": b.hint} for b in missing]


class Unsupported(Failed):
    pass


def sh(argv, **kw):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, **kw)
    except FileNotFoundError:
        raise Failed(f"{argv[0]} is not installed")
    if r.returncode:
        lines = (r.stderr or r.stdout).strip().splitlines()
        raise Failed(lines[-1] if lines else f"exit {r.returncode}")


def find(*candidates):
    """First candidate that exists on PATH or as a file; else the first name, for messages."""
    for c in candidates:
        if shutil.which(c) or os.path.isfile(c):
            return c
    return candidates[0]


def installed(binary):
    return binary is None or bool(shutil.which(binary)) or os.path.isfile(binary)


MAGICK = find("magick", "convert")
FFMPEG = find("ffmpeg")
PANDOC = find("pandoc")
SOFFICE = find("soffice", "/Applications/LibreOffice.app/Contents/MacOS/soffice")
CALIBRE = find("ebook-convert", "/Applications/calibre.app/Contents/MacOS/ebook-convert")
ASSIMP = find("assimp")
BLENDER = find("blender", "/Applications/Blender.app/Contents/MacOS/Blender")
FONTFORGE = find("fontforge")
SEVENZ = find("7z", "7zz")
POTRACE = find("potrace")

# ---- external tools ---------------------------------------------------------

SIPS = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "tif": "tiff", "tiff": "tiff", "gif": "gif", "bmp": "bmp",
        "psd": "psd", "tga": "tga", "jp2": "jp2", "pict": "pict", "heic": "heic", "pdf": "pdf"}
SIPS_READ = set(SIPS) | {"webp", "avif", "jxl", "heif", "icns", "ico", "exr", "hdr",
                         "dng", "cr2", "cr3", "nef", "arw", "raf", "orf", "rw2", "pef", "srw"}
TEXTUTIL = {"txt", "html", "htm", "rtf", "rtfd", "doc", "docx", "odt"}
PANDOC_IN = {"md", "markdown", "html", "htm", "rst", "tex", "latex", "docx", "odt", "epub", "txt",
             "org", "textile", "ipynb", "typ", "dbk", "opml", "rtf", "fb2", "wiki"}
PANDOC_OUT = PANDOC_IN | {"adoc", "asciidoc"}
CALIBRE_IN = FORMATS["ebooks"] | {"docx", "html", "htm", "odt", "pdf", "rtf", "txt", "md", "markdown"}
CALIBRE_OUT = {"azw3", "docx", "epub", "fb2", "htmlz", "lrf", "mobi", "oeb", "pdb", "pdf", "pml", "rb",
               "rtf", "snb", "tcr", "txt", "txtz"}
FF_IMG = {"png", "jpg", "jpeg", "webp", "gif", "apng", "bmp", "tif", "tiff", "tga", "exr", "dpx", "ppm", "pgm",
          "pbm", "pam"}
LO_IMG = {"png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff", "webp", "svg", "emf", "wmf", "eps"}
BLENDER_IO = {  # ext: (import operator, export operator)
    "blend": ("wm.open_mainfile", "wm.save_as_mainfile"),
    "stl": ("wm.stl_import", "wm.stl_export"), "obj": ("wm.obj_import", "wm.obj_export"),
    "ply": ("wm.ply_import", "wm.ply_export"), "fbx": ("import_scene.fbx", "export_scene.fbx"),
    "glb": ("import_scene.gltf", "export_scene.gltf"), "gltf": ("import_scene.gltf", "export_scene.gltf"),
    "dae": ("wm.collada_import", "wm.collada_export"), "abc": ("wm.alembic_import", "wm.alembic_export"),
    "usd": ("wm.usd_import", "wm.usd_export"), "usda": ("wm.usd_import", "wm.usd_export"),
    "usdc": ("wm.usd_import", "wm.usd_export"), "usdz": ("wm.usd_import", "wm.usd_export"),
}


def soffice(i, o):
    return [SOFFICE, "--headless", "--convert-to", ext(o), "--outdir", os.path.dirname(o), i]


def pandoc(i, o):
    return [PANDOC, i, "-o", o] + (["-t", "plain"] if ext(o) == "txt" else [])


def blender(i, o):
    extra = ", export_format='GLTF_SEPARATE'" if ext(o) == "gltf" else ""
    script = ("import bpy; bpy.ops.wm.read_factory_settings(use_empty=True); "
              f"bpy.ops.{BLENDER_IO[ext(i)][0]}(filepath={i!r}); "
              f"bpy.ops.{BLENDER_IO[ext(o)][1]}(filepath={o!r}{extra})")
    return [BLENDER, "-b", "--python-exit-code", "1", "--python-expr", script]


def potrace(i, o):
    """Raster -> SVG is tracing: threshold to a bitmap with ImageMagick, then trace."""
    with tempfile.TemporaryDirectory() as tmp:
        pbm = os.path.join(tmp, "in.pbm")
        sh([MAGICK, i, pbm])
        sh([POTRACE, "-s", "-o", o, pbm])


# ---- native routines --------------------------------------------------------

ARCHIVE = {"zip": "zip", "tar": "tar", "tgz": "gztar", "tbz2": "bztar", "txz": "xztar"}


def archive(i, o):
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "src")
        shutil.unpack_archive(i, src, ARCHIVE[ext(i)])
        shutil.move(shutil.make_archive(os.path.join(tmp, "out"), ARCHIVE[ext(o)], src), o)


def sevenzip(i, o):
    with tempfile.TemporaryDirectory() as tmp:
        sh([SEVENZ, "x", "-y", "-o" + tmp, i])
        sh([SEVENZ, "a", "-y", o, "."], cwd=tmp)


DATA_IN = {"json", "jsonl", "ndjson", "csv", "tsv", "plist", "toml"}
DATA_OUT = DATA_IN - {"toml"}


def data(i, o):
    e = ext(i)
    with open(i, "rb") as f:
        if e == "json":
            value = json.load(f)
        elif e in ("jsonl", "ndjson"):
            value = [json.loads(line) for line in f if line.strip()]
        elif e in ("csv", "tsv"):
            value = list(csv.DictReader(io.TextIOWrapper(f, "utf-8-sig"), delimiter="\t" if e == "tsv" else ","))
        elif e == "plist":
            value = plistlib.load(f)
        else:
            import tomllib
            value = tomllib.load(f)
    e = ext(o)
    rows = value if isinstance(value, list) else [value]
    if e in ("csv", "tsv"):
        if not all(isinstance(r, dict) for r in rows):
            raise Failed("csv/tsv output needs a list of objects")
        keys = list(dict.fromkeys(k for r in rows for k in r))
        with open(o, "w", newline="") as f:
            w = csv.DictWriter(f, keys, delimiter="\t" if e == "tsv" else ",")
            w.writeheader()
            w.writerows(rows)
    elif e == "plist":
        with open(o, "wb") as f:
            plistlib.dump(value, f)
    elif e == "json":
        with open(o, "w") as f:
            json.dump(value, f, indent=2, ensure_ascii=False, default=str)
            f.write("\n")
    else:
        with open(o, "w") as f:
            f.writelines(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows)


# ---- registry ---------------------------------------------------------------
# A backend handles every (input, output) pair in `pairs`; each side is a category name or a
# single extension. `ins`/`outs` optionally narrow it to extension sets. `argv` builds a
# command line; `run` does the work itself. List order is preference.

Backend = collections.namedtuple("Backend", "name bin pairs ins outs argv run hint")

BACKENDS = [
    Backend("potrace", POTRACE, {("images", "images")}, None, {"svg"}, None, potrace, "brew install potrace"),
    Backend("imagemagick", MAGICK, {("images", "images"), ("images", "pdf"), ("pdf", "images"), ("images", "eps"),
                                    ("eps", "images"), ("images", "ps"), ("ps", "images")},
            None, None, lambda i, o: [MAGICK, i, o], None, "brew install imagemagick"),
    Backend("sips", "sips", {("images", "images"), ("images", "pdf"), ("pdf", "images")},
            SIPS_READ, set(SIPS), lambda i, o: ["sips", "-s", "format", SIPS[ext(o)], i, "--out", o], None,
            "built into macOS"),
    Backend("ffmpeg", FFMPEG, {("video", "video"), ("video", "audio"), ("audio", "audio"), ("subtitles", "subtitles"),
                               ("video", "subtitles")} | {("video", e) for e in FF_IMG} | {(e, "video") for e in FF_IMG}
                              | {(a, b) for a in FF_IMG for b in FF_IMG},
            None, None, lambda i, o: [FFMPEG, "-y", "-loglevel", "error", "-i", i, o], None, "brew install ffmpeg"),
    Backend("pandoc", PANDOC, {("documents", "documents"), ("documents", "ebooks"), ("ebooks", "documents"),
                               ("ebooks", "ebooks")},
            PANDOC_IN, PANDOC_OUT, pandoc, None, "brew install pandoc"),
    Backend("libreoffice", SOFFICE, {("documents", "documents")} | {("documents", e) for e in LO_IMG},
            None, None, soffice, None, "brew install --cask libreoffice"),
    Backend("textutil", "textutil", {("documents", "documents")},
            TEXTUTIL, TEXTUTIL, lambda i, o: ["textutil", "-convert", "html" if ext(o) == "htm" else ext(o),
                                              i, "-output", o], None, "built into macOS"),
    Backend("calibre", CALIBRE, {("ebooks", "ebooks"), ("documents", "ebooks"), ("ebooks", "documents")},
            CALIBRE_IN, CALIBRE_OUT, lambda i, o: [CALIBRE, i, o], None, "brew install --cask calibre"),
    Backend("assimp", ASSIMP, {("3d", "3d")}, None, None, lambda i, o: [ASSIMP, "export", i, o], None,
            "brew install assimp"),
    Backend("blender", BLENDER, {("3d", "3d")}, set(BLENDER_IO), set(BLENDER_IO), blender, None,
            "brew install --cask blender"),
    Backend("fontforge", FONTFORGE, {("fonts", "fonts")}, None, None,
            lambda i, o: [FONTFORGE, "-lang=ff", "-c", "Open($1); Generate($2)", i, o], None,
            "brew install fontforge"),
    Backend("archive", None, {("archives", "archives")}, set(ARCHIVE), set(ARCHIVE), None, archive, "built in"),
    Backend("7zip", SEVENZ, {("archives", "archives")}, None, {"7z", "zip", "tar", "wim"}, None, sevenzip,
            "brew install sevenzip"),
    Backend("data", None, {("data", "data")}, DATA_IN, DATA_OUT, None, data, "built in"),
]


def fits(ie, ic, oe, oc):
    return [b for b in BACKENDS
            if any((a == ie or a in ic) and (z == oe or z in oc) for a, z in b.pairs)
            and (b.ins is None or ie in b.ins) and (b.outs is None or oe in b.outs)]


def candidates(i, o, oc=None):
    ie, oe = ext(i), ext(o)
    ic, oc = cats(ie), oc or cats(oe)
    if not ic:
        raise Unsupported(f".{ie} is not in formats/*.txt")
    if not oc:
        raise Unsupported(f".{oe} is not in formats/*.txt")
    fit = fits(ie, ic, oe, oc)
    if not fit:
        raise Unsupported(f"nothing here converts {'/'.join(ic)} to {'/'.join(oc)}")
    ready = [b for b in fit if installed(b.bin)]
    missing = [b for b in fit if not installed(b.bin)]
    if not ready:
        raise Unsupported("needs a tool that is not installed: " + "; ".join(f"{b.name} ({b.hint})" for b in missing), missing)
    return ready, missing


def convert(i, o, force):
    i, o = os.path.abspath(i), os.path.abspath(o)
    if not os.path.isfile(i):
        raise Failed(f"no such file: {i}")
    existed = os.path.exists(o)
    if existed and not force:
        raise Failed(f"{o} exists (use -f to overwrite)")
    errors = []
    ready, missing = candidates(i, o)
    for b in ready:
        try:
            if b.argv:
                sh(b.argv(i, o))
            else:
                b.run(i, o)
            # tools that pick their own output name (LibreOffice) get it moved into place
            guess = os.path.join(os.path.dirname(o), os.path.basename(stem(i)) + "." + ext(o))
            if not os.path.exists(o) and guess != i and os.path.isfile(guess):
                shutil.move(guess, o)
            if not os.path.isfile(o):
                raise Failed("produced no output file")
            return b
        except Failed as e:
            errors.append(f"{b.name}: {e}")
            if not existed and os.path.exists(o):
                os.remove(o)
    if missing:
        errors.append("not installed: " + ", ".join(f"{b.name} ({b.hint})" for b in missing))
    raise Failed("; ".join(errors), missing)


def options(i):
    """Outputs this file can become on this machine, by category."""
    out = {}
    for cat, exts in FORMATS.items():
        for e in sorted(exts):
            try:
                candidates(i, "x." + e, [cat])
                out.setdefault(cat, []).append(e)
            except Unsupported:
                pass
    return out


# ---- cli --------------------------------------------------------------------

def emit(d, as_json):
    if as_json:
        print(json.dumps(d, ensure_ascii=False))
    elif "error" in d:
        print(f"error: {d['input']}: {d['error']}", file=sys.stderr)
    elif "outputs" in d:
        for cat, exts in d["outputs"].items():
            print(f"{cat:<10} " + " ".join("." + e for e in exts))
    else:
        line = f"{d['input']} -> {d['output']}  [{d['backend']}]"
        if d.get("command"):
            line += "\n  " + shlex.join(d["command"])
        if d.get("missing"):
            line += "\n  also possible with: " + ", ".join(f"{m['backend']} ({m['install']})" for m in d["missing"])
        print(line)


def main():
    ap = argparse.ArgumentParser(prog="convert.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="INPUT OUTPUT, or INPUT... with --to")
    ap.add_argument("--to", metavar="EXT", help="output extension; output goes next to each input")
    ap.add_argument("--can", action="store_true",
                    help="plan only: with INPUT OUTPUT shows the tool and command; with just INPUT lists every output that works here")
    ap.add_argument("--list", nargs="?", const="", metavar="CATEGORY", help="list categories, or one category's extensions")
    ap.add_argument("--doctor", action="store_true", help="show which tools are installed")
    ap.add_argument("-f", "--force", action="store_true", help="overwrite an existing output")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args()

    if a.list is not None:
        if a.list and a.list not in FORMATS:
            ap.error(f"no category '{a.list}'; have: {', '.join(FORMATS)}")
        chosen = {c: sorted(FORMATS[c]) for c in ([a.list] if a.list else FORMATS)}
        if a.json:
            print(json.dumps(chosen))
        elif a.list:
            print("\n".join("." + e for e in chosen[a.list]))
        else:
            print("\n".join(f"{c:<10} {len(e)}" for c, e in chosen.items()))
        return
    if a.doctor:
        rows = []
        for b in BACKENDS:
            status = "built in" if b.bin is None else (shutil.which(b.bin) or b.bin if installed(b.bin) else "missing")
            rows.append({"backend": b.name, "installed": status != "missing", "path": status, "install": b.hint})
            if not a.json:
                print(f"{b.name:<12} {status}" + (f"   ({b.hint})" if status == "missing" else ""))
        if a.json:
            print(json.dumps(rows))
        return
    if a.can and len(a.files) == 1 and not a.to:
        i = a.files[0]
        emit({"input": i, "outputs": options(os.path.abspath(i))}, a.json)
        return

    if a.to:
        jobs = [(f, stem(f) + "." + a.to.lstrip(".")) for f in a.files]
    elif len(a.files) == 2:
        jobs = [tuple(a.files)]
    else:
        ap.error("give INPUT OUTPUT, or INPUT... --to EXT")
    code = 0
    for i, o in jobs:
        try:
            if a.can:
                ai, ao = os.path.abspath(i), os.path.abspath(o)
                ready, missing = candidates(ai, ao)
                emit({"ok": True, "plan": True, "input": i, "output": o, "backend": ready[0].name,
                      "backends": [b.name for b in ready],
                      "command": ready[0].argv(ai, ao) if ready[0].argv else None,
                      "missing": [{"backend": b.name, "install": b.hint} for b in missing]}, a.json)
            else:
                b = convert(i, o, a.force)
                emit({"ok": True, "input": i, "output": o, "backend": b.name}, a.json)
        except Failed as e:
            emit({"ok": False, "input": i, "output": o, "error": str(e), "missing": e.missing}, a.json)
            code = max(code, 2 if isinstance(e, Unsupported) else 1)
    sys.exit(code)


if __name__ == "__main__":
    main()
