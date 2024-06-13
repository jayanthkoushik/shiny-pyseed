#!/usr/bin/env python3
# This script populates the placeholders in the source with data, and
# generates `dist/pyseed.py`.

import stat
from pathlib import Path

src_dir = Path("src")
src_pyseed_path = src_dir / "pyseed.py"
data_dir = src_dir / "data"
dist_dir = Path("dist")
dist_pyseed_path = dist_dir / "pyseed.py"

pyseed_data = src_pyseed_path.read_text()

for data_file in data_dir.glob("*"):
    data = data_file.read_text()
    # Placeholders are in the form '!!!<FILENAME>!!!'.
    pyseed_data_sub = pyseed_data.replace(f"!!!{data_file.name}!!!", data)
    if pyseed_data_sub == pyseed_data:
        raise AssertionError(f"no placeholder found for {data_file}")
    pyseed_data = pyseed_data_sub

# Add shebang.
pyseed_data = "#!/usr/bin/env python3\n\n" + pyseed_data

dist_dir.mkdir(exist_ok=True)
dist_pyseed_path.write_text(pyseed_data)
dist_pyseed_path_mode = dist_pyseed_path.stat().st_mode
dist_pyseed_path.chmod(
    dist_pyseed_path_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
)
