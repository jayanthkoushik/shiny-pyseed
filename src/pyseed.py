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
        if any(member.value is self for member in BAREBONES_MODE_IGNORED_CONFIG_KEYS):
            help_txt += " (ignored in barebones mode)"
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
        help_txt = self.description
        if any(member.value is self for member in BAREBONES_MODE_IGNORED_CONFIG_KEYS):
            help_txt += " (ignored in barebones mode)"
        true_help = help_txt
        false_arg = f"--no-{self.name.replace('_', '-')}"
        false_help = f"do not {help_txt}"
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
    barebones = BoolConfigKeySpec("barebones", "create barebones project", False)
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
        "maximum python3 version, for github actions",
        "3.12",
        validate_string_python_version,
    )
    add_py_typed = BoolConfigKeySpec(
        "py_typed", "add 'py.typed' file indicating typing support", True
    )
    update_pc_hooks_on_schedule = BoolConfigKeySpec(
        "pc_cron", "add support for updating pre-commit hooks monthly", True
    )
    add_deps = StrConfigKeySpec(
        "add_deps",
        "additional python dependencies to install (semicolon separated)",
        "",
    )
    add_dev_deps = StrConfigKeySpec(
        "add_dev_deps",
        "additional python dev dependencies to install (semicolon separated)",
        "",
    )
    no_github = BoolConfigKeySpec(
        "no_github",
        "disable github support by not including any github related files",
        False,
    )
    no_doctests = BoolConfigKeySpec(
        "no_doctests", "do not include boilerplate code to load doctests", False
    )


BAREBONES_MODE_IGNORED_CONFIG_KEYS = [
    ConfigKey.url,
    ConfigKey.max_py_version,
    ConfigKey.update_pc_hooks_on_schedule,
    ConfigKey.no_github,
    ConfigKey.no_doctests,
]


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
            if config_key in BAREBONES_MODE_IGNORED_CONFIG_KEYS and config.get(
                ConfigKey.barebones, False
            ):
                continue
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
# FUNCTION TO INITIALIZE PROJECT STRUCTURE
# This function will create the project directory and write data files.
# Template files are formatted with data from config.


def init_project(config: dict[ConfigKey, Any]):
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

    if config[ConfigKey.barebones]:
        pyproject = PYPROJECT_SIMPLE_TEMPLATE.format(
            min_python_version=config[ConfigKey.min_py_version],
            mypy_target_version=f"py3{min_py_minor_ver}",
        )
    else:
        pyproject = PYPROJECT_TEMPLATE.format(
            name_dump=project_name_dump,
            description_dump=json.dumps(config[ConfigKey.description]),
            authors_dump=json.dumps(authors),
            license="MIT" if config[ConfigKey.add_mit_license] else "",
            package=config[ConfigKey.main_pkg],
            min_python_version=config[ConfigKey.min_py_version],
            mypy_target_version=f"py3{min_py_minor_ver}",
        )
    vwritetext(project_path / "pyproject.toml", pyproject)

    if not config[ConfigKey.barebones]:
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

    pre_commit_config = (
        PRE_COMMIT_CONFIG_SIMPLE if config[ConfigKey.barebones] else PRE_COMMIT_CONFIG
    )

    if config[ConfigKey.barebones]:
        for fpath, fdata in [
            ("README.md", readme),
            (".cspell.json", CSPELL_CONFIG),
            (".editorconfig", EDITORCONFIG),
            (".gitignore", GITIGNORE),
            (".pre-commit-config.yaml", pre_commit_config),
        ]:
            vwritetext(project_path / fpath, fdata)

        main_pkg_dir = project_path / config[ConfigKey.main_pkg]
        vprint(f"+ MKDIR {main_pkg_dir}", file=sys.stderr)
        main_pkg_dir.mkdir(parents=True)
        vtouch(main_pkg_dir / "__init__.py")

        vtouch(project_path / "project-words.txt")
        return

    if not config[ConfigKey.no_github]:
        min_py_minor_version = int(config[ConfigKey.min_py_version].split(".")[1])
        max_py_minor_version = int(config[ConfigKey.max_py_version].split(".")[1])
        py_minor_versions = range(min_py_minor_version, max_py_minor_version + 1)
        py_version_strs = [
            f'"3.{minor_version}"' for minor_version in py_minor_versions
        ]
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

        gh_workflows_dir = project_path / ".github" / "workflows"
        vprint(f"+ MKDIR {gh_workflows_dir}", file=sys.stderr)
        gh_workflows_dir.mkdir(parents=True)

        for fname, fdata in [
            ("check-pr.yml", CHECK_PR_WORKFLOW),
            ("release-new-version.yml", RELEASE_NEW_VERSION_WORKFLOW),
            ("create-github-release.yml", CREATE_GITHUB_RELEASE_WORKFLOW),
            ("publish-to-pypi.yml", PUBLISH_TO_PYPI_WORKFLOW),
            ("deploy-project-site.yml", DEPLOY_PROJECT_SITE_WORKFLOW),
            ("run-tests.yml", run_tests_workflow),
            ("update-pre-commit-hooks.yml", update_pc_hooks_workflow),
        ]:
            vwritetext(gh_workflows_dir / fname, fdata)

    scripts_dir = Path("scripts")
    main_pkg_dir = Path("src") / config[ConfigKey.main_pkg]
    tests_dir = Path("tests")
    www_dir = Path("www")

    for directory in [
        scripts_dir,
        main_pkg_dir,
        tests_dir,
        www_dir / "src",
        www_dir / "theme" / "overrides",
    ]:
        vprint(f"+ MKDIR {project_path / directory}", file=sys.stderr)
        (project_path / directory).mkdir(parents=True)

    script_files_data = [
        (scripts_dir / "gen_site_usage_pages.py", GEN_SITE_USAGE_PAGES_SCRIPT),
        (scripts_dir / "make_docs.py", MAKE_DOCS_SCRIPT),
    ]
    if config[ConfigKey.no_github]:
        script_files_data.append(
            (scripts_dir / "release_new_version.py", RELEASE_NEW_VERSION_SCRIPT)
        )
    else:
        script_files_data.extend(
            [
                (
                    scripts_dir / "commit_and_tag_version.py",
                    COMMIT_AND_TAG_VERSION_SCRIPT,
                ),
                (scripts_dir / "verify_pr_commits.py", VERIFY_PR_COMMITS_SCRIPT),
            ]
        )

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
        *script_files_data,
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

    if not config[ConfigKey.no_doctests]:
        test_doctests_py = TEST_DOCTESTS_TEMPLATE.format(
            main_pkg=config[ConfigKey.main_pkg]
        )
        vwritetext(project_path / "tests" / "test_doctests.py", test_doctests_py)

    web_src_dir = project_path / "www" / "src"
    for link_src, link_tgt in [
        ("CHANGELOG.md", "CHANGELOG.md"),
        ("LICENSE.md", "LICENSE.md"),
        ("README.md", "index.md"),
    ]:
        vprint(f"+ SYMLINK {web_src_dir / link_tgt} -> {link_src}", file=sys.stderr)
        os.symlink(Path("..") / ".." / link_src, web_src_dir / link_tgt)

    for script_path in (project_path / scripts_dir).glob("*"):
        vprint(f"+ CHMOD+x {script_path}", file=sys.stderr)
        os.chmod(
            script_path,
            stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH,
        )


########################################################################
# FUNCTION TO INSTALL AND SETUP NEW PROJECT
# This function will create a git repository, install dependencies, and
# create an initial commit.


def create_project(config: dict[ConfigKey, Any]):
    project_path = Path(config[ConfigKey.project])
    scripts_dir = Path("scripts")

    vprint(file=sys.stderr)
    vprint(f"+ CHDIR {project_path}", file=sys.stderr)
    os.chdir(project_path)

    vrun(["git", "init", "-b", "master"])

    vrun(["poetry", "install", "--all-extras"])
    dev_dependencies = ["pre-commit", "ruff", "mypy"]
    if not config[ConfigKey.barebones]:
        dev_dependencies.extend(
            ["sphinx", "git+https://github.com/liran-funaro/sphinx-markdown-builder"]
        )
    add_dev_deps = [
        dep
        for dep_raw in config[ConfigKey.add_dev_deps].split(";")
        if (dep := dep_raw.strip())
    ]
    if add_dev_deps:
        dev_dependencies.extend(add_dev_deps)
    vrun(["poetry", "add", "--group", "dev", *dev_dependencies])

    if not config[ConfigKey.barebones]:
        site_deps = [
            "mkdocstrings[python-legacy]",
            "mkdocs-material",
            "mkdocs-gen-files",
            "mkdocs-literate-nav",
            "git+https://github.com/jimporter/mike",
        ]
        vrun(["poetry", "add", "--group", "site", *site_deps])

    add_deps = [
        dep
        for dep_raw in config[ConfigKey.add_deps].split(";")
        if (dep := dep_raw.strip())
    ]
    if add_deps:
        vrun(["poetry", "add", *add_deps])

    vrun(["poetry", "run", "pre-commit", "install"])
    vrun(["poetry", "run", "pre-commit", "autoupdate"])

    if not config[ConfigKey.barebones]:
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
    env["SKIP"] = "cspell"
    commit_msg = (
        "Initial commit" if config[ConfigKey.barebones] else "chore: initial commit"
    )
    vrun(["git", "commit", "-m", commit_msg], env=env)

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
            f"(https://github.com/settings/personal-access-tokens/new) "
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
        init_project(config)
        create_project(config)
        project_created = True
        if (
            config_mode == ConfigMode.non_interactive
            or config[ConfigKey.barebones]
            or config[ConfigKey.no_github]
        ):
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


PYPROJECT_TEMPLATE = r"""!!!pyproject.template.toml!!!
"""

PYPROJECT_SIMPLE_TEMPLATE = r"""!!!pyproject_simple.template.toml!!!
"""

MKDOCS_CONFIG_TEMPLATE = r"""!!!mkdocs_config.template.yml!!!
"""

MIT_LICENSE_TEMPLATE = r"""!!!mit_license.template.md!!!
"""

README_TEMPLATE = r"""!!!readme.template.md!!!
"""

COMMITLINT_RC = r"""!!!commitlint_rc.yaml!!!
"""

CSPELL_CONFIG = r"""!!!cspell_config.json!!!
"""

EDITORCONFIG = r"""!!!editorconfig.ini!!!
"""

GITATTRIBUTES = r"""!!!gitattributes!!!
"""

GITIGNORE = r"""!!!gitignore!!!
"""

PRE_COMMIT_CONFIG = r"""!!!pre_commit_config.yaml!!!
"""

PRE_COMMIT_CONFIG_SIMPLE = r"""!!!pre_commit_config_simple.yaml!!!
"""

PRETTIER_IGNORE = r"""!!!prettier_ignore!!!
"""

PRETTIER_RC = r"""!!!prettier_rc.js!!!
"""

CHECK_PR_WORKFLOW = r"""!!!check_pr_workflow.yml!!!
"""

RELEASE_NEW_VERSION_WORKFLOW = r"""!!!release_new_version_workflow.yml!!!
"""

CREATE_GITHUB_RELEASE_WORKFLOW = r"""!!!create_github_release_workflow.yml!!!
"""

PUBLISH_TO_PYPI_WORKFLOW = r"""!!!publish_to_pypi_workflow.yml!!!
"""

DEPLOY_PROJECT_SITE_WORKFLOW = r"""!!!deploy_project_site_workflow.yml!!!
"""

RUN_TESTS_WORKFLOW_TEMPLATE = r"""!!!run_tests_workflow.template.yml!!!
"""

UPDATE_PRE_COMMIT_HOOKS_WORKFLOW_TEMPLATE = r"""!!!update_pre_commit_hooks_workflow.template.yml!!!
"""

COMMIT_AND_TAG_VERSION_SCRIPT = r"""!!!commit_and_tag_version_script.py!!!
"""

GEN_SITE_USAGE_PAGES_SCRIPT = r"""!!!gen_site_usage_pages_script.py!!!
"""

MAKE_DOCS_SCRIPT = r"""!!!make_docs_script.py!!!
"""

VERIFY_PR_COMMITS_SCRIPT = r"""!!!verify_pr_commits_script.py!!!
"""

RELEASE_NEW_VERSION_SCRIPT = r"""!!!release_new_version.py!!!
"""

INIT_PY = r"""from ._version import __version__
"""

VERSION_PY = r"""__version__ = "0.0.0"  # managed by `poetry-dynamic-versioning`
"""

THEME_OVERRIDE_MAIN = r"""!!!theme_override_main.html!!!
"""

TEST_DOCTESTS_TEMPLATE = r"""!!!test_doctests.template.py!!!
"""


########################################################################
# ENTRY POINT


if __name__ == "__main__":
    ensure_tty = True
    main()
