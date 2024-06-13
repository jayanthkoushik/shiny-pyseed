#!/usr/bin/env python3

from importlib import import_module
from pathlib import Path

import mkdocs_gen_files

PYSRC_PATH = Path(__file__).parent.parent / "src"
USAGE_REL_DIR = "usage"  # relative to the docs

nav = mkdocs_gen_files.Nav()

for py_path in sorted(PYSRC_PATH.rglob("*.py")):
    py_rel_path = py_path.relative_to(PYSRC_PATH)
    mod_rel_path = py_rel_path.with_suffix("")
    doc_rel_path = py_rel_path.with_suffix(".md")
    doc_path = Path(USAGE_REL_DIR, doc_rel_path)
    mod_path_parts = tuple(mod_rel_path.parts)

    if mod_path_parts[-1] == "__init__":
        # Create an index file with all the exported objects in the
        # init file (`__all__`).
        mod_path_parts = mod_path_parts[:-1]
        doc_rel_path = doc_rel_path.with_name("index.md")
        doc_path = doc_path.with_name("index.md")

        mod_name = ".".join(mod_path_parts)
        mod = import_module(mod_name)

        with mkdocs_gen_files.open(doc_path, "w") as f:
            print(f"# {mod_name}\n", file=f)
            if mod.__doc__:
                print(mod.__doc__, end="\n\n", file=f)
            for obj_name in getattr(mod, "__all__", []):
                print(f"::: {mod_name}.{obj_name}", file=f)
                print("    options:", file=f)
                print("      show_root_heading: true", file=f)
                print("      show_root_full_path: false", file=f)
    elif mod_path_parts[-1].startswith("_"):
        continue
    else:
        with mkdocs_gen_files.open(doc_path, "w") as f:
            mod_name = ".".join(mod_path_parts)
            print(f"# {mod_name}", file=f)
            print(f"::: {mod_name}", file=f)

    nav[mod_path_parts] = doc_rel_path.as_posix()
    mkdocs_gen_files.set_edit_path(doc_path, py_rel_path)

with mkdocs_gen_files.open(f"{USAGE_REL_DIR}/SUMMARY.md", "w") as nav_file:
    nav_file.writelines(nav.build_literate_nav())
