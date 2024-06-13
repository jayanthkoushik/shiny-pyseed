#!/usr/bin/env python3

import subprocess
import sys
from argparse import ArgumentParser

parser = ArgumentParser()
parser.add_argument("-f", "--first-release", type=str, choices=["true", "false"])
parser.add_argument("-r", "--release-version", nargs="?", type=str)
parser.add_argument("-p", "--pre-release", type=str, choices=["true", "false"])
parser.add_argument("-t", "--pre-release-tag", nargs="?", type=str)
parser.add_argument("--dry-run", action="store_true")
args = parser.parse_args()

cmd_args = []

if args.first_release == "true":
    cmd_args.append("--skip.changelog")
    cmd_args.append("--skip.commit")

if args.release_version:
    cmd_args.extend(["-r", args.release_version])
elif args.first_release == "true":
    cmd_args.extend(["-r", "1.0.0"])

if args.pre_release == "true":
    cmd_args.append("-p")
    if args.pre_release_tag:
        cmd_args.append(args.pre_release_tag)

if args.dry_run:
    cmd_args.append("--dry-run")

cmd = ["npx", "commit-and-tag-version", *cmd_args]
print(f"+ {' '.join(cmd)}", file=sys.stderr)
subprocess.run(cmd, check=True)
