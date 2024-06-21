#!/usr/bin/env python3

import os
import subprocess
import sys
from argparse import ArgumentParser, BooleanOptionalAction, RawTextHelpFormatter
from getpass import getpass


#######################################################################
# ARGUMENT PARSING

arg_parser = ArgumentParser(formatter_class=RawTextHelpFormatter)
arg_parser.add_argument(
    "-f",
    "--first-release",
    action="store_true",
    help="Create the first release. If version is not specified,\n"
    "it will be set to '1.0.0'. No changelog will be generated.",
)
arg_parser.add_argument(
    "-r",
    "--release-version",
    type=str,
    metavar="VERSION",
    help="Release as the provided version. Should be a valid semvar\n"
    "version, or one of 'major', 'minor', or 'patch'. If not\n"
    "provided, version is determined automatically from commits\n"
    "since the previous release.",
)
arg_parser.add_argument(
    "-p",
    "--pre-release",
    action="store_true",
    help="Make a pre-release. If a custom version is specified, or a first\n"
    "release is being made, a pre-release tag must also be provided,\n"
    "or the custom version should be of the form\n"
    "'<major>.<minor>.<patch>-<pre-release-tag>'.",
)
arg_parser.add_argument(
    "-t",
    "--pre-release-tag",
    type=str,
    metavar="TAG",
    help="Use provided tag for pre-release. This only has effect\n"
    "if making a pre-release, and will create release with version\n"
    "'<major>.<minor>.<patch>-<pre-release-tag>-<pre-release-version>'.",
)
arg_parser.add_argument(
    "--git-push",
    action=BooleanOptionalAction,
    help="Whether to run `git push` after creating release commit.\n"
    "True by default.",
    default=True,
)
arg_parser.add_argument(
    "--pypi-publish",
    action=BooleanOptionalAction,
    help="Whether to publish the project to PyPI. Requires an access token.\n"
    "The token can be provided with an environment variable named PYPI_TOKEN.\n"
    "If this is not available, the user is prompted for it. True by default.",
    default=True,
)
arg_parser.add_argument(
    "--dry-run", action="store_true", help="Only show what commands will be executed."
)
args = arg_parser.parse_args()


#######################################################################
# CALL npx commit-and-tag-version

commit_and_tag_cmd = ["npx", "commit-and-tag-version"]

if args.first_release:
    commit_and_tag_cmd.append("--skip.changelog")
    commit_and_tag_cmd.append("--skip.commit")

if args.release_version:
    commit_and_tag_cmd.extend(["-r", args.release_version])
elif args.first_release:
    commit_and_tag_cmd.extend(["-r", "1.0.0"])

if args.pre_release:
    commit_and_tag_cmd.append("-p")
    if args.pre_release_tag:
        commit_and_tag_cmd.append(args.pre_release_tag)

if args.dry_run:
    commit_and_tag_cmd.append("--dry-run")

print(f"+ {' '.join(commit_and_tag_cmd)}", file=sys.stderr)
subprocess.run(commit_and_tag_cmd, check=True)


#######################################################################
# CALL git push

if args.git_push:
    push_cmd = ["git", "push", "--follow-tags", "origin", "master"]
    print(f"+ {' '.join(push_cmd)}", file=sys.stderr)
    if not args.dry_run:
        subprocess.run(push_cmd, check=True)


#######################################################################
# CALL poetry publish

if args.pypi_publish:
    pypi_publish_cmd = ["poetry", "publish", "-u", "__token__", "-p", "PYPI_TOKEN"]
    print(f"+ {' '.join(pypi_publish_cmd)}", file=sys.stderr)
    if not args.dry_run:
        if "PYPI_TOKEN" in os.environ:
            pypi_token = os.environ["PYPI_TOKEN"]
        else:
            pypi_token = getpass("PyPI access token: ")
        pypi_publish_cmd[-1] = pypi_token

        subprocess.run(pypi_publish_cmd, check=True)
