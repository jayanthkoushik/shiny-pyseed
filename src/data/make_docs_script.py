#!/usr/bin/env python3

import re
import shlex
import subprocess
import sys
from pathlib import Path

docs_dir = Path("docs")
build_dir = docs_dir / "_build"
src_dir = Path("src")
pkg_dirs = list(src_dir.glob("*"))

# fmt: off
apidoc_cmd = [
    "sphinx-apidoc",
    "-o", str(build_dir),
    "-d", "1",
    "--module-first",
    "--tocfile=index",
    "--separate",
    *list(map(str, pkg_dirs)),
]
# fmt: on
print(f"+ {shlex.join(apidoc_cmd)}", file=sys.stderr)
subprocess.run(apidoc_cmd, check=True, text=True)

doctrees_dir = build_dir / ".doctrees"
rsts = list(build_dir.glob("*.rst"))

# fmt: off
build_cmd = [
    "sphinx-build",
    "-C",
    "-D", "extensions=sphinx.ext.autodoc,sphinx.ext.napoleon",
    "-D", "default_role=samp",
    "-D", "autodoc_member_order=bysource",
    "-D", "autodoc_typehints=description",
    "-D", "highlight_language=python",
    "-b", "markdown",
    "-c", str(docs_dir),
    "-d", str(doctrees_dir),
    str(build_dir), str(docs_dir),
    # *list(map(str, rsts)),
]
# fmt: on
print(f"+ {shlex.join(build_cmd)}", file=sys.stderr)
subprocess.run(build_cmd, check=True, text=True)

# Remove tralining spaces and newlines from the generated files.
for fname in docs_dir.glob("**/*.md"):
    with open(fname, "r") as f:
        fdata = f.read()

    fdata_fixed = re.sub(r" *(?=$)", "", fdata, flags=re.MULTILINE)
    fdata_fixed = re.sub("\n+(?=$)", "", fdata_fixed)
    if fdata_fixed != fdata:
        with open(fname, "w") as f:
            print(fdata_fixed, file=f)
