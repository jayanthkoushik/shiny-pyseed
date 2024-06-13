#!/usr/bin/env python3

from __future__ import annotations

import shlex
import sys

########################################################################
# ENSURE WE ARE NOT INSIDE A VIRTUAL ENVIRONMENT


if sys.prefix != sys.base_prefix:
    print("error: cannot run from inside virtual env", file=sys.stderr)
    sys.exit(-1)


########################################################################
# CHECK PYTHON VERSION IS SUFFICIENT


NEED_PYTHON_MINOR_VERSION = 9

if sys.version_info < (3, NEED_PYTHON_MINOR_VERSION):
    print(
        "error: need python 3.%d or higher" % NEED_PYTHON_MINOR_VERSION, file=sys.stderr
    )
    sys.exit(-1)


########################################################################

import json
import os
import re
import shutil
import stat
import subprocess
import textwrap
from abc import ABC, abstractmethod
from argparse import ArgumentParser
from contextlib import contextmanager
from enum import Enum
from getpass import getpass
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from typing import Any, Callable, Optional, Union
from urllib.parse import urlparse

########################################################################
# GLOBAL VARIABLES


verbose = True
pwd_abs = Path(os.curdir).absolute()
ensure_tty = False


########################################################################
# VERBOSITY SENSITIVE VERSIONS OF COMMON FUNCTIONS


def vprint(*args, **kwargs):
    if verbose:
        print(*args, **kwargs)


def vwritetext(path, text, *args, **kwargs):
    vprint(f"+ WRITE {path}", file=sys.stderr)
    text = text.strip() + "\n"
    path.write_text(text, *args, **kwargs)


def vtouch(path, *args, **kwargs):
    vprint(f"+ TOUCH {path}", file=sys.stderr)
    path.touch(*args, **kwargs)


def vrun(cmd: list[str], *args, **kwargs) -> CompletedProcess:
    vprint(f"\n+ RUN {shlex.join(cmd)}", file=sys.stderr)
    show_output_on_err = False
    if "check" not in kwargs:
        kwargs["check"] = True
    if "text" not in kwargs:
        kwargs["text"] = True
    if not verbose and not any(
        _k in kwargs for _k in ["capture_output", "stdout", "stderr"]
    ):
        show_output_on_err = True
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.STDOUT
    try:
        return subprocess.run(cmd, *args, **kwargs)  # noqa: PLW1510
    except CalledProcessError as e:
        if show_output_on_err:
            print(e.stdout, file=sys.stderr)
        elif kwargs.get("capture_output"):
            print(e.stderr, file=sys.stderr)
        raise


########################################################################
# UTILS FOR GETTING USER FROM GIT CONFIG


def get_git_user() -> Optional[str]:  # output is formatted as 'name <email>'
    user_data = {}
    for key in ["name", "email"]:
        try:
            proc = subprocess.run(
                ["git", "config", f"user.{key}"],
                check=True,
                capture_output=True,
                text=True,
            )
            user_data[key] = proc.stdout.strip()
            if not user_data[key]:
                return None
        except CalledProcessError:
            return None
    return f"{user_data['name']} <{user_data['email']}>"


def extract_name_from_name_email(name_email: str) -> str:
    # 'My Name <my@email>' -> 'My Name'.
    match = re.search(r"(.+) <.+>", name_email, flags=re.DOTALL)
    if match is not None:
        return match.groups()[0].strip()
    return name_email


########################################################################
# VALIDATION FUNCTIONS FOR CONFIG
# Each of these functions takes a string, and returns a validation
# error, or None if the input is valid.


def validate_string_non_empty(inp: str) -> Optional[str]:
    if not isinstance(inp, str):
        return "not a string"
    if not inp:
        return "cannot be empty"
    return None


def validate_string_python_version(inp: str) -> Optional[str]:
    if not isinstance(inp, str):
        return "not a string"
    if re.match(r"3(\.[0-9]+){1,2}$", inp) is None:
        return "not a valid python3 version"
    minor_version = int(inp.split(".")[1])
    if minor_version < NEED_PYTHON_MINOR_VERSION:
        return (
            f"can only create projects supporting python 3.{NEED_PYTHON_MINOR_VERSION}+"
        )
    return None


def validate_string_url(inp: str) -> Optional[str]:
    if not isinstance(inp, str):
        return "not a string"
    # mkdocs needs urls to start with 'http[s]://'.
    parse_result = urlparse(inp)
    if parse_result.scheme not in ["http", "https"] or not parse_result.netloc:
        return "url must start with 'http[s]://'"
    return None


########################################################################
# FUNCTIONS FOR GETTING USER INPUT INTERACTIVELY
# If the global `ensure_tty` is `True`, and `sys.stdin` is not a tty,
# `/dev/tty` is explicitly opened to read input. There is no support
# for Windows.


@contextmanager
def tty_stdin():
    if not ensure_tty or sys.stdin.isatty():
        yield
        return
    if not os.path.exists("/dev/tty"):
        raise OSError("tty not available for reading input")
    old_stdin = sys.stdin
    try:
        sys.stdin = open("/dev/tty", mode="r")  # noqa: SIM115
        yield
    finally:
        sys.stdin.close()
        sys.stdin = old_stdin


def get_input(
    prompt: str,
    default: Optional[str] = None,
    validator: Optional[Callable[[str], Optional[str]]] = None,
) -> str:
    if default is not None:
        prompt += f" [default: '{default}']"
    prompt += ": "
    while True:
        with tty_stdin():
            try:
                inp = input(prompt)
            except KeyboardInterrupt:
                sys.exit(1)
        if not inp and default is not None:
            inp = default
        inp = inp.strip()
        if validator is None:
            return inp
        validation_error = validator(inp)
        if validation_error is None:
            return inp
        print(f"error: {validation_error}", file=sys.stderr)


def get_yes_no_input(prompt: str, default: Optional[bool] = None) -> bool:
    def validate_yn(inp: str) -> Optional[str]:
        if re.match(r"y|yes|n|no", inp) is None:
            return "enter [y]es/[n]o"
        return None

    prompt += " ([y]es/[n]o)"
    default_yn = None if default is None else ("yes" if default else "no")
    raw_inp = get_input(prompt, default_yn, validate_yn)
    return raw_inp.startswith("y")


########################################################################
# INTERFACE FOR MAKING CALLS TO THE GITHUB API


class GitHubAPI:
    class Error(Exception):
        def __init__(self, err: Union[Exception, str]):
            if isinstance(err, Exception):
                errmsg = f"{err.__class__.__name__}: {err}"
            else:
                errmsg = str(err)
            super().__init__(f"Error calling GitHub API: {errmsg}")

    def __init__(self, gh_token: str):
        self.gh_token = gh_token

    def call(
        self,
        endpoint: str,
        call_type: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        curl_cmd = ["curl", "-L"]
        curl_cmd.extend(["-H", "Accept: application/vnd.github+json"])
        curl_cmd.extend(["-H", "X-GitHub-Api-Version: 2022-11-28"])
        curl_cmd.extend(["-H", f"Authorization: Bearer {self.gh_token}"])
        if call_type is not None:
            curl_cmd.extend(["-X", call_type.upper()])
        api_url = f"https://api.github.com/{endpoint}"
        curl_cmd.append(api_url)
        if data is not None:
            curl_cmd.extend(["-d", json.dumps(data)])

        vprint(f"\n+ CALL {api_url}", file=sys.stderr)
        pdone = subprocess.run(curl_cmd, check=True, capture_output=True)
        if not pdone.stdout:
            return {}
        try:
            response_data = json.loads(pdone.stdout)
        except json.JSONDecodeError as e:
            raise self.Error(e) from None
        return response_data

    @contextmanager
    def setup_secrets_manager(self):
        # Uploading secrets to GitHub requires encrypting them with
        # `libsodium`. Since this may not be available on the host
        # system, encryption is done in the virtual environment
        # created for the seeded project. `setup_secrets_manager`
        # handles this as a context manager.
        secrets_manager = self.SecretsManager(self)
        secrets_manager._install_deps()
        try:
            yield secrets_manager
        finally:
            secrets_manager._uninstall_deps()

    class SecretsManager:
        def __init__(self, gh_api: GitHubAPI):
            self.gh_api = gh_api
            self.do_uninstall = False

        def _install_deps(self):
            vrun(["poetry", "run", "pip", "install", "--require-virtualenv", "pynacl"])

        def _uninstall_deps(self):
            if self.do_uninstall:
                vrun(
                    [
                        "poetry",
                        "run",
                        "pip",
                        "uninstall",
                        "--require-virtualenv",
                        "-y",
                        "pynacl",
                    ]
                )

        def upload_actions_secret(
            self, repo_owner: str, repo_name: str, secret_name: str, secret: str
        ) -> dict[str, Any]:
            public_key_data = self.gh_api.call(
                f"repos/{repo_owner}/{repo_name}/actions/secrets/public-key"
            )
            try:
                public_key_id, public_key = (
                    public_key_data["key_id"],
                    public_key_data["key"],
                )
            except KeyError:
                raise GitHubAPI.Error(f"response:\n{public_key_data}") from None

            secret_encrypted = self.encrypt(public_key, secret)
            return self.gh_api.call(
                f"repos/{repo_owner}/{repo_name}/actions/secrets/{secret_name}",
                "PUT",
                {"encrypted_value": secret_encrypted, "key_id": public_key_id},
            )

        def encrypt(self, public_key: str, secret: str) -> str:
            encrypt_script = textwrap.dedent(
                f"""
                from base64 import b64encode

                import nacl.public
                import nacl.encoding

                repo_public_key = "{public_key}"
                secret = "{secret}"

                repo_public_key_sealed_box = nacl.public.SealedBox(
                    nacl.public.PublicKey(
                        repo_public_key.encode("utf-8"), nacl.encoding.Base64Encoder()
                    )
                )
                secret_bytes = secret.encode("utf-8")
                secret_encrypted = repo_public_key_sealed_box.encrypt(secret_bytes)
                secret_encrypted_b64 = b64encode(secret_encrypted).decode("utf-8")
                print(secret_encrypted_b64)
                """
            )

            pdone = vrun(
                ["poetry", "run", "-q", "python"],
                input=encrypt_script,
                capture_output=True,
            )
            return pdone.stdout.strip()


########################################################################
# CONFIG KEY SPECIFICATION
# Configuration keys implement the `ConfigKeySpec` interface, which
# provides methods for reading the config value interactively or from
# the command line (by adding an argument to an `ArgumentParser`).


class ConfigKeySpec(ABC):
    @abstractmethod
    def get_value_interactively(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    def add_arg_to_argparser(
        self, argparser: ArgumentParser, no_default_required: bool = False
    ) -> None:
        raise NotImplementedError


class StrConfigKeySpec(ConfigKeySpec):
    def __init__(
        self,
        name: str,
        description: str,
        default: Any = None,
        validator: Optional[Callable[[str], Optional[str]]] = None,
    ):
        self.name = name
        self.description = description
        self.default = default
        self.validator = validator

    def get_value_interactively(self) -> str:
        return get_input(
            prompt=self.description, default=self.default, validator=self.validator
        )

    def add_arg_to_argparser(
        self, argparser: ArgumentParser, no_default_required: bool = False
    ) -> None:
        def add_type(s: str) -> str:
            if self.validator is None:
                return s
            validation_error = self.validator(s)
            if validation_error is None:
                return s
            raise ValueError(validation_error)

        name = self.name
        arg_name = f"-{name}" if len(name) == 1 else f"--{name.replace('_', '-')}"
        help_txt = self.description
        if self.default is not None:
            help_txt += f" [default: '{self.default}']"
        arg_default = None if no_default_required else self.default
        arg_required = False if no_default_required else self.default is None
        argparser.add_argument(
            arg_name,
            type=add_type,
            help=help_txt,
            default=arg_default,
            required=arg_required,
            dest=self.name,
        )


class BoolConfigKeySpec(ConfigKeySpec):
    def __init__(self, name: str, description: str, default: Any = None):
        self.name = name
        self.description = description
        self.default = default

    def get_value_interactively(self) -> bool:
        return get_yes_no_input(prompt=self.description, default=self.default)

    def add_arg_to_argparser(
        self, argparser: ArgumentParser, no_default_required: bool = False
    ) -> None:
        # Boolean config keys are parsed from the command line
        # in three ways:
        #   * If the default value is false, a `--<key>` argument is
        #     added, which will set the config to true.
        #   * If the default value is true, a `--no-<key>` argument is
        #     added, which will set the config to false.
        #   * If there is no default value, both the above arguments
        #     are added to a mutually exclusive group.
        true_arg = f"--{self.name.replace('_', '-')}"
        true_help = self.description
        false_arg = f"--no-{self.name.replace('_', '-')}"
        false_help = f"do not {self.description}"
        if self.default is False:
            argparser.add_argument(
                true_arg,
                help=true_help,
                action="store_true",
                dest=self.name,
                default=None if no_default_required else False,
            )
        elif self.default is True:
            argparser.add_argument(
                false_arg,
                help=false_help,
                action="store_false",
                dest=self.name,
                default=None if no_default_required else True,
            )
        elif self.default is None:
            arg_required = not no_default_required
            grp = argparser.add_mutually_exclusive_group(required=arg_required)
            grp.add_argument(
                true_arg, action="store_true", dest=self.name, help=true_help
            )
            grp.add_argument(
                false_arg, action="store_false", dest=self.name, help=false_help
            )
            argparser.set_defaults(**{self.name: None})
        else:
            raise TypeError(f"expected boolean default: got {self.default}")


########################################################################
# CONFIGURATION KEYS


class ConfigKey(Enum):
    project = StrConfigKeySpec("path", "project path", None, validate_string_non_empty)
    description = StrConfigKeySpec("desc", "project description", "")
    url = StrConfigKeySpec("url", "project docs site", "")
    main_pkg = StrConfigKeySpec(
        "pkg", "main package name (same as project name if empty)", ""
    )
    add_mit_license = BoolConfigKeySpec("mit", "include mit license", True)
    authors = StrConfigKeySpec(
        "authors", "authors (comma separated 'name <email>')", get_git_user()
    )
    min_py_version = StrConfigKeySpec(
        "pym",
        "minimum python3 version",
        f"3.{NEED_PYTHON_MINOR_VERSION}",
        validate_string_python_version,
    )
    max_py_version = StrConfigKeySpec(
        "pyM",
        "maximum python3 version (for github actions)",
        "3.12",
        validate_string_python_version,
    )
    add_typing_extensions = BoolConfigKeySpec(
        "typing_extensions", "add 'typing_extensions' as a dependency", False
    )
    add_py_typed = BoolConfigKeySpec(
        "py_typed", "add 'py.typed' file indicating typing support", True
    )
    update_pc_hooks_on_schedule = BoolConfigKeySpec(
        "pc_cron", "add support for updating pre-commit hooks monthly", True
    )


########################################################################
# FUNCTIONS FOR GETTING CONFIG VALUES
# A configuration is a dictionary with `ConfigKey` cases as keys. For
# instance, `config[ConfigKey.project]` will contain the project name.
# Interactive mode is enabled when the script is executed without any
# arguments, but the special `-i/--interactive` argument can be used to
# explicitly trigger interactive mode. In this case, other arguments
# will be used to set the default values for interactive mode.


class ConfigMode(Enum):
    interactive = 0
    non_interactive = 1


def parse_cmdline_args() -> tuple[ConfigMode, Optional[dict[ConfigKey, Any]]]:
    if len(sys.argv) <= 1:
        return (ConfigMode.interactive, None)

    config_mode = (
        ConfigMode.interactive
        if (
            "--interactive" in sys.argv
            or any(
                # Single letter arguments can appear together:
                # '-i', '-si', '-his' etc.
                re.match(r"^-[a-z]*i[a-z]*$", arg) is not None
                for arg in sys.argv
            )
        )
        else ConfigMode.non_interactive
    )

    argparser = ArgumentParser()
    argparser.add_argument(
        "-i",
        "--interactive",
        help="configure project creation interactively",
        action="store_true",
    )
    argparser.add_argument(
        "-s", "--silent", help="suppress output", action="store_true"
    )

    for config_key in ConfigKey:
        config_key.value.add_arg_to_argparser(
            argparser, no_default_required=config_mode == ConfigMode.interactive
        )

    args = argparser.parse_args()
    args_dict = vars(args)

    if args.silent:
        global verbose  # noqa: PLW0603
        verbose = False

    config: dict[ConfigKey, Any] = {}
    for config_key in ConfigKey:
        config_val = args_dict.get(config_key.value.name, None)
        # If in interactive mode, only read the config if present, to
        # set the default value.
        if config_mode != ConfigMode.interactive or config_val is not None:
            config[config_key] = config_val

    return (config_mode, config)


def get_conf_interactively(
    base_config: Optional[dict[ConfigKey, Any]] = None,
) -> dict[ConfigKey, Any]:
    config: dict[ConfigKey, Any] = base_config.copy() if base_config is not None else {}
    for config_key in ConfigKey:
        if config_key not in config:
            config_val = config_key.value.get_value_interactively()
            config[config_key] = config_val
        try:
            if config_key == ConfigKey.project:
                project_name = Path(config[ConfigKey.project]).stem
                ConfigKey.main_pkg.value.default = project_name.replace("-", "_")
        except AttributeError:
            continue
    return config


def get_conf() -> tuple[ConfigMode, dict[ConfigKey, Any]]:
    config_mode, base_config = parse_cmdline_args()
    if config_mode == ConfigMode.interactive:
        config = get_conf_interactively(base_config)
    elif base_config is not None:
        config = base_config
    else:
        config = {}

    try:
        if not config[ConfigKey.main_pkg]:
            config[ConfigKey.main_pkg] = (
                Path(config[ConfigKey.project]).stem.lower().replace("-", "_")
            )
    except AttributeError:
        pass
    return config_mode, config


########################################################################
# FUNCTION TO CREATE NEW PROJECT STRUCTURE


def create_project(config: dict[ConfigKey, Any]):
    authors = [
        author
        for author_raw in config[ConfigKey.authors].split(",")
        if (author := author_raw.strip())
    ]
    author_names = [extract_name_from_name_email(author) for author in authors]
    comma_sep_author_names = ", ".join(author_names)

    project_path = Path(config[ConfigKey.project])
    project_name = project_path.stem
    project_name_dump = json.dumps(project_name)
    project_path.mkdir(parents=True)

    min_py_minor_ver = config[ConfigKey.min_py_version].split(".")[1]

    vwritetext(
        project_path / "pyproject.toml",
        PYPROJECT_TEMPLATE.format(
            name_dump=project_name_dump,
            description_dump=json.dumps(config[ConfigKey.description]),
            authors_dump=json.dumps(authors),
            license="MIT" if config[ConfigKey.add_mit_license] else "",
            package=config[ConfigKey.main_pkg],
            min_python_version=config[ConfigKey.min_py_version],
            mypy_target_version=f"py3{min_py_minor_ver}",
        ),
    )

    vprint(f"+ WRITE {project_path / 'mkdocs.yml'}", file=sys.stderr)
    vwritetext(
        project_path / "mkdocs.yml",
        MKDOCS_CONFIG_TEMPLATE.format(
            name_dump=project_name_dump,
            site_url=config[ConfigKey.url],
            description_dump=json.dumps(f"Documentation for '{project_name}'."),
            author_dump=json.dumps(comma_sep_author_names),
            copyright_dump=json.dumps(f"Copyright (c) {comma_sep_author_names}"),
        ),
    )

    license_data = (
        MIT_LICENSE_TEMPLATE.format(author=comma_sep_author_names)
        if config[ConfigKey.add_mit_license]
        else ""
    )
    vwritetext(project_path / "LICENSE.md", license_data)

    readme = README_TEMPLATE.format(
        title=project_name, description=config[ConfigKey.description]
    ).strip()

    pre_commit_config = PRE_COMMIT_CONFIG

    min_py_minor_version = int(config[ConfigKey.min_py_version].split(".")[1])
    max_py_minor_version = int(config[ConfigKey.max_py_version].split(".")[1])
    py_minor_versions = range(min_py_minor_version, max_py_minor_version + 1)
    py_version_strs = [f'"3.{minor_version}"' for minor_version in py_minor_versions]
    run_tests_workflow = RUN_TESTS_WORKFLOW_TEMPLATE.format(
        python_versions=", ".join(py_version_strs)
    )

    update_pc_hooks_workflow = UPDATE_PRE_COMMIT_HOOKS_WORKFLOW_TEMPLATE.format(
        schedule=(
            '  schedule:\n    - cron: "0 0 1 * *"\n'
            if config[ConfigKey.update_pc_hooks_on_schedule]
            else ""
        )
    )

    gh_workflows_dir = Path(".github") / "workflows"
    scripts_dir = Path("scripts")
    main_pkg_dir = Path("src") / config[ConfigKey.main_pkg]
    tests_dir = Path("tests")
    www_dir = Path("www")

    for directory in [
        gh_workflows_dir,
        scripts_dir,
        main_pkg_dir,
        tests_dir,
        www_dir / "src",
        www_dir / "theme" / "overrides",
    ]:
        vprint(f"+ MKDIR {project_path / directory}", file=sys.stderr)
        (project_path / directory).mkdir(parents=True)

    for fpath, fdata in [
        ("README.md", readme),
        (".commitlintrc.yaml", COMMITLINT_RC),
        (".cspell.json", CSPELL_CONFIG),
        (".editorconfig", EDITORCONFIG),
        (".gitattributes", GITATTRIBUTES),
        (".gitignore", GITIGNORE),
        (".pre-commit-config.yaml", pre_commit_config),
        (".prettierignore", PRETTIER_IGNORE),
        (".prettierrc.js", PRETTIER_RC),
        (gh_workflows_dir / "check-pr.yml", CHECK_PR_WORKFLOW),
        (gh_workflows_dir / "release-new-version.yml", RELEASE_NEW_VERSION_WORKFLOW),
        (gh_workflows_dir / "run-tests.yml", run_tests_workflow),
        (gh_workflows_dir / "update-pre-commit-hooks.yml", update_pc_hooks_workflow),
        (scripts_dir / "commit_and_tag_version.py", COMMIT_AND_TAG_VERSION_SCRIPT),
        (scripts_dir / "gen_site_usage_pages.py", GEN_SITE_USAGE_PAGES_SCRIPT),
        (scripts_dir / "make_docs.py", MAKE_DOCS_SCRIPT),
        (scripts_dir / "verify_pr_commits.py", VERIFY_PR_COMMITS_SCRIPT),
        (main_pkg_dir / "__init__.py", INIT_PY),
        (main_pkg_dir / "_version.py", VERSION_PY),
        (www_dir / "theme" / "overrides" / "main.html", THEME_OVERRIDE_MAIN),
    ]:
        vwritetext(project_path / fpath, fdata)

    vtouch(project_path / "project-words.txt")
    vtouch(project_path / "CHANGELOG.md")
    if config[ConfigKey.add_py_typed]:
        vtouch(project_path / main_pkg_dir / "py.typed")
    vtouch(project_path / "tests" / "__init__.py")

    web_src_dir = project_path / "www" / "src"
    for link_src, link_tgt in [
        ("CHANGELOG.md", "CHANGELOG.md"),
        ("LICENSE.md", "LICENSE.md"),
        ("README.md", "index.md"),
    ]:
        vprint(f"+ SYMLINK {web_src_dir / link_tgt} -> {link_src}", file=sys.stderr)
        os.symlink(Path("..") / ".." / link_src, web_src_dir / link_tgt)

    for fpath in (project_path / scripts_dir).glob("*"):
        vprint(f"+ CHMOD+x {fpath}", file=sys.stderr)
        os.chmod(
            fpath,
            stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH,
        )

    vprint(file=sys.stderr)
    vprint(f"+ CHDIR {project_path}", file=sys.stderr)
    os.chdir(project_path)

    vrun(["git", "init", "-b", "master"])

    vrun(["poetry", "install", "--all-extras"])
    if config[ConfigKey.add_typing_extensions]:
        vrun(["poetry", "add", "typing_extensions"])
    dev_dependencies = [
        "pre-commit",
        "ruff",
        "mypy",
        "sphinx",
        "git+https://github.com/liran-funaro/sphinx-markdown-builder",
        "mkdocstrings[python-legacy]",
        "mkdocs-material",
        "mkdocs-gen-files",
        "mkdocs-literate-nav",
        "git+https://github.com/jimporter/mike",
    ]
    vrun(["poetry", "add", "--group", "dev", *dev_dependencies])

    vrun(["poetry", "run", "pre-commit", "install"])
    vrun(["poetry", "run", "pre-commit", "autoupdate"])
    vrun(
        [
            "poetry",
            "run",
            "pre-commit",
            "run",
            "prettier",
            "--files",
            "pyproject.toml",
            "mkdocs.yml",
            "LICENSE.md",
            "README.md",
        ],
        check=False,
    )
    vrun(["poetry", "run", "python", str(scripts_dir / "make_docs.py")])
    vrun(["poetry", "run", "mkdocs", "build"])

    vrun(["git", "add", "."])
    env = os.environ.copy()
    env["SKIP"] = "cspell,test"
    vrun(["git", "commit", "-m", "chore: initial commit"], env=env)

    vprint(f"\nsuccessfully initialized project at {project_path}", file=sys.stderr)


########################################################################
# FUNCTION TO CONFIGURE GITHUB FOR THE NEWLY CREATED PROJECT
# This step is skipped when not in interactive mode, since passing
# tokens (for GitHub authentication) through the command line is not
# safe; further more, the API cannot create personal access tokens,
# so fully scripted GitHub setup is not possible any way.


def setup_github(config: dict[ConfigKey, Any]):
    api_access_token = getpass(
        "enter personal access token for github api "
        "(with 'administration:write' and 'secrets:write' permissions): "
    )
    gh_api = GitHubAPI(api_access_token)

    project_path = Path(config[ConfigKey.project])
    project_name = project_path.stem

    git_use_ssh = get_yes_no_input(
        "use ssh for connecting to github (instead of https)", True
    )

    repo_creation_response = gh_api.call(
        "user/repos",
        "POST",
        {
            "name": project_name,
            "description": config[ConfigKey.description],
            "homepage": config[ConfigKey.url],
        },
    )
    try:
        repo_owner = repo_creation_response["owner"]["login"]
        repo_url = repo_creation_response["html_url"]
        repo_origin = repo_creation_response["ssh_url"] if git_use_ssh else repo_url
    except KeyError:
        raise GitHubAPI.Error(f"response:\n{repo_creation_response}") from None

    vprint("\n+ UPDATE pyproject.toml", file=sys.stderr)
    with open("pyproject.toml", "r") as f:
        pyproject_data = f.read()
    pyproject_data = re.sub(
        r"# repository = .*", f'repository = "{repo_url}"', pyproject_data, count=1
    )
    with open("pyproject.toml", "w") as f:
        print(pyproject_data, file=f, end="")
    vrun(["poetry", "lock", "--no-update"])

    vprint("\n+ UPDATE mkdocs.yml", file=sys.stderr)
    with open("mkdocs.yml", "r") as f:
        mkdocs_data = f.read()
    mkdocs_data = re.sub(
        r"# repo_url: .*", f'repo_url: "{repo_url}"', mkdocs_data, count=1
    )
    with open("mkdocs.yml", "w") as f:
        print(mkdocs_data, file=f, end="")

    vrun(["git", "add", "pyproject.toml", "mkdocs.yml"])
    vrun(["git", "commit", "--amend", "--no-edit"])
    vrun(["git", "remote", "add", "origin", repo_origin])
    vrun(["git", "push", "-u", "origin", "master"])

    gh_api.call(
        f"repos/{repo_owner}/{project_name}/branches/master/protection",
        "PUT",
        {
            "required_status_checks": None,
            "enforce_admins": None,
            "required_pull_request_reviews": None,
            "restrictions": None,
            "required_linear_history": True,
        },
    )

    gh_api.call(
        (
            f"repos/{repo_owner}/{project_name}/"
            f"branches/master/protection/required_pull_request_reviews"
        ),
        "PATCH",
        {"required_approving_review_count": 0},
    )

    gh_api.call(
        f"repos/{repo_owner}/{project_name}/tags/protection", "POST", {"pattern": "v*"}
    )

    gh_api.call(
        f"repos/{repo_owner}/{project_name}/actions/permissions/workflow",
        "PUT",
        {
            "default_workflow_permissions": "read",
            "can_approve_pull_request_reviews": True,
        },
    )

    with gh_api.setup_secrets_manager() as gh_secrets_manager:
        release_token = getpass(
            f"\ncreate a personal access token with 'contents:write' "
            f"and 'pull_requests:write' permissions for this project's repo "
            f"({repo_owner}/{project_name}), and enter it here "
            f"(or leave empty to skip this step): "
        )
        if release_token:
            gh_secrets_manager.upload_actions_secret(
                repo_owner, project_name, "REPO_PAT", release_token
            )

        pypi_access_token = getpass(
            "\nenter token for uploading releases to pypi "
            "(or leave empty to skip this step): "
        )
        if pypi_access_token:
            gh_secrets_manager.upload_actions_secret(
                repo_owner, project_name, "PYPI_TOKEN", pypi_access_token
            )

        gh_secrets_manager.do_uninstall = get_yes_no_input(
            "\nuninstall dependencies used for encryption of tokens", False
        )

    vprint("\nsuccessfully configured github for project", file=sys.stderr)


########################################################################
# MAIN


def main():
    config_mode, config = get_conf()
    project_created = False

    try:
        create_project(config)
        project_created = True
        if config_mode == ConfigMode.non_interactive:
            return

        do_setup_github = get_yes_no_input(
            "\ncreate and configure github repository for project", default=True
        )
        if not do_setup_github:
            return

        setup_github(config)

    except (KeyboardInterrupt, OSError, CalledProcessError, GitHubAPI.Error) as e:
        print(e, file=sys.stderr)
        if project_created:
            sys.exit(2)
        if config_mode == ConfigMode.interactive:
            do_clean = get_yes_no_input(
                f"clean project folder '{config[ConfigKey.project]}'", default=True
            )
            if do_clean:
                try:
                    os.chdir(pwd_abs)
                    shutil.rmtree(config[ConfigKey.project])
                except OSError as ce:
                    print(ce, file=sys.stderr)
        sys.exit(1)


########################################################################
# FILE DATA
# File data is inserted by the build script, replacing placeholders
# of the form '!!!<DATA FILE>!!!'.


PYPROJECT_TEMPLATE = r"""[tool.poetry]
name = {name_dump}
description = {description_dump}
authors = {authors_dump}
version = "0.0.0" # version is managed by `poetry-dynamic-versioning`
packages = [{{ include = "{package}", from = "src" }}]
include = [
  {{ path = "tests", format = "sdist" }},
  {{ path = "docs", format = "sdist" }},
  {{ path = "CHANGELOG.md", format = "sdist" }},
]
# repository = ""
license = "{license}"
readme = "README.md"
# keywords = [
# ]
# classifiers = [
# ]

[tool.poetry.dependencies]
python = "^{min_python_version}"

[tool.poetry.extras]

[tool.poetry.group.dev.dependencies]

[tool.poetry-dynamic-versioning]
enable = true
vcs = "git"
style = "semver"

[tool.poetry-dynamic-versioning.substitution]
files = ["*/_version.py"]

[tool.ruff]
target-version = "{mypy_target_version}"

[tool.ruff.format]
skip-magic-trailing-comma = true

[tool.ruff.lint]
select = [
  "F",
  "E4",
  "E7",
  "E9",
  "W",
  #"I",
  "N",
  "D2",
  "D3",
  "D4",
  "ANN0",
  "ANN2",
  "ANN4",
  "B",
  "A",
  "G",
  "SIM",
  #"TCH",
  "PLC",
  "PLE",
  "PLW",
  "RUF",
]
ignore-init-module-imports = true

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401", "F403", "F405"]

[tool.ruff.lint.flake8-annotations]
allow-star-arg-any = true
ignore-fully-untyped = true
suppress-dummy-args = true
suppress-none-returning = true

[tool.ruff.lint.isort]
combine-as-imports = true
split-on-trailing-comma = false

[tool.ruff.lint.pycodestyle]
max-doc-length = 72

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.mypy]
ignore_missing_imports = true

[build-system]
requires = ["poetry-core>=1.0.0", "poetry-dynamic-versioning"]
build-backend = "poetry_dynamic_versioning.backend"

"""

MKDOCS_CONFIG_TEMPLATE = r"""site_name: {name_dump}
site_url: "{site_url}"
# repo_url: ""
site_description: {description_dump}
site_author: {author_dump}
copyright: {copyright_dump}

docs_dir: www/src
site_dir: www/_site

nav:
  - Home:
      - index.md
      - License: LICENSE.md
      - Changelog: CHANGELOG.md
  - API reference: usage/

plugins:
  - search
  - mike:
      canonical_version: latest
  - gen-files:
      scripts:
        - scripts/gen_site_usage_pages.py
  - literate-nav
  - mkdocstrings:
      handlers:
        python:
          options:
            show_root_toc_entry: false
            members_order: source
            show_if_no_docstring: true
            show_signature_annotations: true
            show_source: false
            filters:
              - "!^_"

markdown_extensions:
  - smarty
  - pymdownx.highlight
  - pymdownx.superfences
  - pymdownx.caret
  - pymdownx.betterem:
      smart_enable: all
  - toc:
      permalink: true

extra:
  version:
    provider: mike

theme:
  name: material
  custom_dir: www/theme/overrides
  features:
    - content.code.copy
    - navigation.instant
    - navigation.instant.progres
    - navigation.tabs
    - navigation.indexes
    - navigation.top
    - search.suggest
  palette:
    - media: "(prefers-color-scheme: light)"
      scheme: default
      toggle:
        icon: material/weather-sunny
        name: Switch to dark mode
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      toggle:
        icon: material/weather-night
        name: Switch to light mode

"""

MIT_LICENSE_TEMPLATE = r"""# MIT License

Copyright (c) {author}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

"""

README_TEMPLATE = r"""# {title}

{description}

"""

COMMITLINT_RC = r"""extends: ["@commitlint/config-conventional"]

rules:
  # Rule values are of the form [<level>, <always/never>, [<value>]].
  # Levels: 0 (disable), 1 (warning), 2 (error).
  header-max-length: [2, always, 72]
  body-max-line-length: [2, always, 72]
  footer-max-line-length: [2, always, 72]

  body-leading-blank: [2, always]
  footer-leading-blank: [2, always]

"""

CSPELL_CONFIG = r"""{
  "$schema": "https://raw.githubusercontent.com/streetsidesoftware/cspell/main/cspell.schema.json",
  "version": "0.2",
  "language": "en-US",
  "dictionaries": ["softwareTerms", "python", "filetypes", "project-words"],
  "allowCompoundWords": true,
  "maxDuplicateProblems": 1,
  "dictionaryDefinitions": [
    {
      "name": "project-words",
      "path": "project-words.txt",
      "addWords": true
    }
  ]
}

"""

EDITORCONFIG = r"""root = true

[*]
charset = utf-8
end_of_line = lf
trim_trailing_whitespace = true
insert_final_newline = true
indent_style = space

[*.{py,sh}]
indent_size = 4

[*.{yml,yaml,toml,md,json,html}]
indent_size = 2

"""

GITATTRIBUTES = r""".git*                       export-ignore
.commitlintrc.yaml          export-ignore
.editorconfig               export-ignore
.pre-commit-config.yaml     export-ignore
.prettierignore             export-ignore
.prettierrc.js              export-ignore
.cspell.json                export-ignore
project-words.txt           export-ignore

"""

GITIGNORE = r"""dist/
docs/_build/
www/_site/
.mypy_cache/
.ruff_cache/
__pycache__/
.ipynb_checkpoints/

"""

PRE_COMMIT_CONFIG = r"""default_install_hook_types: [pre-commit, commit-msg]
default_stages: [pre-commit]

repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: check-case-conflict
      - id: check-symlinks
      - id: destroyed-symlinks
      - id: end-of-file-fixer
      - id: mixed-line-ending
      - id: trailing-whitespace
      - id: check-merge-conflict
      - id: check-vcs-permalinks
      - id: detect-private-key

  - repo: https://github.com/streetsidesoftware/cspell-cli
    rev: v8.6.0
    hooks:
      - id: cspell
        name: Spell check docs
        files: "docs/.*\\.md|README.md"

  - repo: https://github.com/alessandrojcm/commitlint-pre-commit-hook
    rev: v9.13.0
    hooks:
      - id: commitlint
        name: Lint commit message
        entry: commitlint -e -s
        stages: [commit-msg]
        additional_dependencies:
          - "@commitlint/config-conventional"
      - id: commitlint
        name: Lint commit message from file in $COMMIT_MSG_FILE
        entry: commitlint -E COMMIT_MSG_FILE -s
        stages: [manual]
        additional_dependencies:
          - "@commitlint/config-conventional"

  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v4.0.0-alpha.8
    hooks:
      - id: prettier
        name: "Prettify non-code files"
        entry: prettier --write --ignore-unknown
        additional_dependencies:
          - prettier
          - prettier-plugin-toml

  - repo: local
    hooks:
      - id: format
        name: Format Python files
        language: system
        entry: poetry run ruff format
        types: [python]
      - id: lint
        name: Lint Python files
        language: system
        entry: poetry run ruff check
        types: [python]
        pass_filenames: false
      - id: mypy
        name: Type check Python files
        entry: poetry run mypy .
        language: system
        types: [python]
        pass_filenames: false
      - id: test
        name: Run unit tests
        language: system
        entry: poetry run python -m unittest
        types: [python]
        exclude: "scripts/.*\\.py|www/.*\\.py"
        pass_filenames: false
      - id: docs
        name: Build docs
        entry: poetry run python scripts/make_docs.py
        language: system
        files: "src/.*\\.py|docs/make\\.sh"
        pass_filenames: false
      - id: nbstrip
        name: Remove metadata from notebooks
        entry: poetry run jupyter nbconvert --inplace --ClearMetadataPreprocessor.enabled=True
        language: system
        types: [jupyter]

"""

PRETTIER_IGNORE = r""".gitattributes
docs/*.md
CHANGELOG.md
poetry.lock

"""

PRETTIER_RC = r"""// https://github.com/prettier/prettier/issues/15388#issuecomment-1717746872
const config = {
  plugins: [require.resolve("prettier-plugin-toml")],
};

module.exports = config;

"""

CHECK_PR_WORKFLOW = r"""name: Check pull request

on: pull_request

jobs:
  run-pre-commit-hooks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pipx install poetry
      - uses: actions/setup-python@v5
        with:
          python-version-file: pyproject.toml
          cache: poetry
      - run: poetry install --all-extras
      - run: SKIP=test poetry run pre-commit run --all-files
      - name: Verify commit messages
        run: ./scripts/verify_pr_commits.py
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  call-run-tests:
    uses: ./.github/workflows/run-tests.yml
    with:
      fail-fast: false

"""

RELEASE_NEW_VERSION_WORKFLOW = r"""name: Create and publish a new release

on:
  workflow_dispatch:
    inputs:
      first-release:
        description: >
          Create the first release. If version is not specified,
          it will be set to '1.0.0'. No changelog will be generated.
        type: boolean
        required: false
        default: false
      version:
        description: >
          Release as the provided version. Should be a valid semvar
          version, or one of 'major', 'minor', or 'patch'. If not
          provided, version is determined automatically from commits
          since the previous release.
        type: string
        required: false
        default: ""
      pre-release:
        description: >
          Make a pre-release. If a custom version is specified, or a first
          release is being made, a pre-release tag must also be provided,
          or the custom version should be of the form
          '<major>.<minor>.<patch>-<pre-release-tag>'.
        type: boolean
        required: false
        default: false
      pre-release-tag:
        description: >
          Use provided tag for pre-release. This only has effect
          if making a pre-release, and will create release with version
          '<major>.<minor>.<patch>-<pre-release-tag>-<pre-release-version>'.
        type: string
        required: false
        default: ""
      publish-to-pypi:
        description: >
          Publish the project to PyPI. Requires a repository secret named
          'PYPI_TOKEN' with a suitable API key.
        type: boolean
        required: false
        default: true

concurrency:
  group: ${{ github.workflow }}
  cancel-in-progress: true

jobs:
  call-run-tests:
    uses: ./.github/workflows/run-tests.yml
    with:
      fail-fast: true

  create-release:
    runs-on: ubuntu-latest
    needs: call-run-tests
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.REPO_PAT }}
          fetch-depth: 0
      - uses: actions/setup-node@v4

      - run: pipx install poetry
      - uses: actions/setup-python@v5
        with:
          python-version-file: pyproject.toml
          cache: poetry
      - run: poetry self add "poetry-dynamic-versioning[plugin]"
      - run: poetry install --all-extras

      - run: SKIP=test poetry run pre-commit run --all-files

      - name: Configure git
        run: |
          git config --global user.name "${{ github.actor }}"
          git config --global user.email \
            "${{ github.actor_id }}+${{ github.actor }}@users.noreply.github.com"

      - name: Bump version and create changelog
        run: >
          ./scripts/commit_and_tag_version.py
          -f ${{ inputs.first-release }}
          -r ${{ inputs.version }}
          -p ${{ inputs.pre-release }}
          -t ${{ inputs.pre-release-tag }}

      - run: git push --follow-tags origin master

      - run: npx conventional-github-releaser -p angular
        env:
          CONVENTIONAL_GITHUB_RELEASER_TOKEN: ${{ secrets.REPO_PAT }}

      - run: poetry build
      - run: poetry publish -u __token__ -p $PYPI_TOKEN
        if: ${{ inputs.publish-to-pypi }}
        env:
          PYPI_TOKEN: ${{ secrets.PYPI_TOKEN }}

      - name: Get latest git tag
        id: tag
        run: echo "tag=$( git describe --tags --abbrev=0 )" >> $GITHUB_OUTPUT
      - name: Extract major and minor versions of latest release
        id: version
        run: |
          echo "version=$( echo ${{ steps.tag.outputs.tag }} \
            | sed -E 's/^v([0-9]+)\.([0-9]+)\..*$/\1.\2/' )" >> $GITHUB_OUTPUT
      - name: Publish site for new release
        if: ${{ ! inputs.pre-release }}
        run: |
          poetry run mike set-default --allow-undefined latest
          poetry run mike deploy --update-aliases --push --allow-empty \
            ${{ steps.version.outputs.version }} latest

"""

RUN_TESTS_WORKFLOW_TEMPLATE = r"""name: Run unit tests

on:
  workflow_call:
    inputs:
      fail-fast:
        type: boolean
        required: false
        default: true

jobs:
  main:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: [{python_versions}]
      fail-fast: ${{{{ inputs.fail-fast }}}}
    runs-on: ${{{{ matrix.os }}}}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{{{ matrix.python-version }}}}
      - run: pip install poetry
      - run: poetry lock
      - run: poetry install --only main --all-extras
      - run: poetry run python -m unittest -v

"""

UPDATE_PRE_COMMIT_HOOKS_WORKFLOW_TEMPLATE = r"""name: Update pre-commit hooks

on:
  workflow_dispatch:
{schedule}
permissions:
  contents: write
  pull-requests: write

jobs:
  pre-commit-autoupdate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pipx install pre-commit
      - run: pre-commit autoupdate
      - uses: peter-evans/create-pull-request@v6
        with:
          token: ${{ secrets.REPO_PAT }}
          commit-message: "chore: update pre-commit hooks"
          branch: update-pre-commit-hooks
          title: Update pre-commit hooks
          labels: automated,chore

"""

COMMIT_AND_TAG_VERSION_SCRIPT = r"""#!/usr/bin/env python3

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

"""

GEN_SITE_USAGE_PAGES_SCRIPT = r"""#!/usr/bin/env python3

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

"""

MAKE_DOCS_SCRIPT = r"""#!/usr/bin/env python3

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

"""

VERIFY_PR_COMMITS_SCRIPT = r"""#!/usr/bin/env python3

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

"""

INIT_PY = r"""from ._version import __version__
"""

VERSION_PY = r"""__version__ = "0.0.0"  # managed by `poetry-dynamic-versioning`
"""

THEME_OVERRIDE_MAIN = r"""{% extends "base.html" %} {% block outdated %} You are viewing an old version of
this page.
<a href="{{ '../' ~ base_url }}">
  <strong>Click here to go to latest version.</strong>
</a>
{% endblock %}

"""


########################################################################
# ENTRY POINT


if __name__ == "__main__":
    ensure_tty = True
    main()
