# format lists

One extension per line, alphabetical, one file per category. `convert.py` reads these at
startup; the file name is the category.

Rule for inclusion: the format is an open standard, has a published spec, or is already
read/written by permissively-licensed open-source tools (ffmpeg, ImageMagick, LibreOffice,
Pandoc, Calibre, Assimp/Blender, libarchive, FontForge). File formats themselves aren't
copyrightable; what gets you sued is DRM circumvention and shipping patented codecs
without a license.

Left out on purpose:
- DRM-wrapped files: .m4p, .acsm, .kfx, DRM'd .azw/.azw3 (the DRM-free ones are fine)
- .dwg (use .dxf), .sldprt/.prt and other closed CAD natives
- .lit, .ace, .sit (dead and closed)

Notes:
- .rar: decompress only — the unrar license forbids writing RAR
- .h264/.h265/.hevc/.heic/.aac: patent-encumbered codecs; fine via the system or ffmpeg
  for personal use, check licensing before selling
- .fbx: Autodesk-owned but readable/writable via Assimp and Blender
- .stl appears in 3d.txt (mesh); the EBU subtitle .stl was left out to avoid the clash
- .mod and .drc appear twice on purpose (tracker audio vs JVC video; Dirac video vs Draco mesh);
  the converter resolves them from the other side of the job
