#!/usr/bin/env python3

import json
import os
import subprocess
import sys
from tempfile import NamedTemporaryFile

github_ref_name = os.environ["GITHUB_REF_NAME"]
# GITHUB_REF_NAME is of the form "<pr_number>/merge" for pull requests.
pr_num = github_ref_name.split("/")[0]

gh_cmd = ["gh", "pr", "view", pr_num, "--json", "commits"]
try:
    gh_proc = subprocess.run(gh_cmd, check=True, capture_output=True, text=True)
except subprocess.CalledProcessError as e:
    print(e.stderr, file=sys.stderr)
    sys.exit(e.returncode)

gh_output_json = json.loads(gh_proc.stdout)
commits = gh_output_json["commits"]
commit_msgs = [
    f"{commit['messageHeadline']}\n\n{commit['messageBody']}".strip()
    for commit in commits
]

pre_commit_cmd = [
    "poetry",
    "run",
    "pre-commit",
    "run",
    "--hook-stage",
    "manual",
    "commitlint",
]
ret_code = 0
for commit_msg in commit_msgs:
    with NamedTemporaryFile(mode="w") as f:
        os.environ["COMMIT_MSG_FILE"] = f.name
        print(f"{commit_msg}\n", file=sys.stderr)
        print(commit_msg, file=f)
        pre_commit_proc = subprocess.run(pre_commit_cmd, check=False, text=True)
        if pre_commit_proc.returncode != 0:
            ret_code = 1
        print("-" * 80, file=sys.stderr)

sys.exit(ret_code)
