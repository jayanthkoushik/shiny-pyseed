import contextlib
import os
import re
import subprocess
import sys
import textwrap
from argparse import ArgumentError, ArgumentParser
from contextlib import contextmanager
from enum import Enum
from io import StringIO
from pathlib import Path
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase, mock, skipIf, skipUnless
from unittest.mock import MagicMock, patch

HAVE_NACL: bool
try:
    import nacl.encoding  # type: ignore
    import nacl.public  # type: ignore

    HAVE_NACL = True
except ImportError:
    HAVE_NACL = False

HAVE_YAML: bool
try:
    import yaml

    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

HAVE_TOML: bool
try:
    import tomllib

    HAVE_TOML = True
except ImportError:
    HAVE_TOML = False

sys.path.insert(0, "dist")

import pyseed

if not __debug__:
    pyseed.verbose = False
pwd_abs = Path(os.curdir).absolute()

GH_USER = "jayanthkoushik"
GH_REPO = "shiny-pyseed"


@contextmanager
def inside_temp_dir():
    temp_dir = TemporaryDirectory()
    try:
        os.chdir(temp_dir.name)
        yield temp_dir.name
    finally:
        os.chdir(pwd_abs)
        temp_dir.cleanup()


@contextmanager
def inside_temp_poetry_dir():
    temp_dir = TemporaryDirectory()
    try:
        env = os.environ.copy()
        env["POETRY_VIRTUALENVS_IN_PROJECT"] = "true"
        pyseed.vrun(["poetry", "new", temp_dir.name])
        os.chdir(temp_dir.name)
        yield temp_dir.name
    finally:
        os.chdir(pwd_abs)
        temp_dir.cleanup()


class TestGetGitUser(TestCase):
    def test_get_git_user_returns_configured_value(self):
        with inside_temp_dir():
            subprocess.run(["git", "init", "-q"], check=True)
            with (Path(".git") / "config").open("w") as f:
                print(
                    textwrap.dedent("""\
                    [user]
                        name = "Dummy User"
                        email = "dummy@example.com"
                    """),
                    file=f,
                )

            git_user = pyseed.get_git_user()
            self.assertEqual(git_user, "Dummy User <dummy@example.com>")

    def test_get_git_user_returns_none_if_key_absent(self):
        completed_process_mock = MagicMock()
        completed_process_mock.stdout = ""
        with patch("pyseed.subprocess.run", return_value=completed_process_mock):
            git_user = pyseed.get_git_user()
            self.assertIsNone(git_user)

    def test_get_git_user_returns_none_if_cmd_fails(self):
        with patch(
            "pyseed.subprocess.run",
            side_effect=CalledProcessError(returncode=1, cmd=""),
        ):
            git_user = pyseed.get_git_user()
            self.assertIsNone(git_user)


class TestExtractNameFromNameEmail(TestCase):
    def test_extract_name_from_name_email_gets_correct_string(self):
        name_email = "Dummy User <dummy@example.com>"
        name = pyseed.extract_name_from_name_email(name_email)
        self.assertEqual(name, "Dummy User")

    def test_extract_name_from_name_email_is_noop_on_bad_input(self):
        for bad_name_email in ["Dummy User", "Dummy User <dummy@example.com", ""]:
            with self.subTest(bad_name_email):
                name = pyseed.extract_name_from_name_email(bad_name_email)
                self.assertEqual(name, bad_name_email)


class TestValidateStringNonEmpty(TestCase):
    def test_validate_string_non_empty_returns_none_for_non_empty_string(self):
        self.assertIsNone(pyseed.validate_string_non_empty("empty"))

    def test_validate_string_non_empty_returns_error_for_empty_or_non_string(self):
        for inp in ["", 1]:
            with self.subTest(inp):
                ret = pyseed.validate_string_non_empty(inp)
                self.assertIsNotNone(ret)
                self.assertIsInstance(ret, str)


class TestValidateStringPythonVersion(TestCase):
    def test_validate_string_python_version_returns_none_for_valid_versions(self):
        for inp in ["3.10.11", "3.10", "3.123.456"]:
            with self.subTest(inp):
                self.assertIsNone(pyseed.validate_string_python_version(inp))

    def test_validate_string_python_version_returns_error_for_invalid_versions(self):
        for inp in [3.10, "3.2", "2.12", "asdf", "3.10.asdf", "3.10.11-alpha"]:
            with self.subTest(inp):
                ret = pyseed.validate_string_python_version(inp)
                self.assertIsNotNone(ret)
                self.assertIsInstance(ret, str)


class TestValidateStringUrl(TestCase):
    def test_validate_string_url_returns_none_for_valid_url(self):
        for inp in ["http://example.com", "https://www.example.com"]:
            with self.subTest(inp):
                self.assertIsNone(pyseed.validate_string_url(inp))

    def test_validate_string_url_returns_error_if_not_http(self):
        for inp in [
            "example.com",
            "ftp://example.com",
            "http:example.com",
            "http//example.com",
        ]:
            with self.subTest(inp):
                ret = pyseed.validate_string_url(inp)
                self.assertIsNotNone(ret)
                self.assertIsInstance(ret, str)


class TestGetInput(TestCase):
    def test_get_input_returns_entered_value(self):
        with patch.multiple("sys", stdin=StringIO("hello, world"), stdout=StringIO()):
            inp = pyseed.get_input("")
        self.assertEqual(inp, "hello, world")

    def test_get_input_shows_prompt(self):
        with StringIO() as mock_stdout:
            with patch.multiple("sys", stdin=StringIO("\n"), stdout=mock_stdout):
                pyseed.get_input("test prompt")
            mock_stdout.seek(0)
            self.assertEqual(mock_stdout.read(), "test prompt: ")

    def test_get_input_shows_default_in_prompt(self):
        with StringIO() as mock_stdout:
            with patch.multiple("sys", stdin=StringIO("\n"), stdout=mock_stdout):
                pyseed.get_input("", default="dummy default")
            mock_stdout.seek(0)
            self.assertIn("dummy default", mock_stdout.read())

    def test_get_input_returns_default_if_no_input(self):
        with patch.multiple("sys", stdin=StringIO("\n"), stdout=StringIO()):
            inp = pyseed.get_input("", default="default value")
        self.assertEqual(inp, "default value")

    def test_get_input_ignores_default_if_input(self):
        with patch.multiple("sys", stdin=StringIO("hello, world"), stdout=StringIO()):
            inp = pyseed.get_input("", default="default value")
        self.assertEqual(inp, "hello, world")

    def test_get_input_calls_validator(self):
        validator = MagicMock(return_value=None)
        with patch.multiple("sys", stdin=StringIO("hello, world"), stdout=StringIO()):
            pyseed.get_input("", validator=validator)
        validator.assert_called_once_with("hello, world")

    def test_get_input_shows_validator_error(self):
        validator = MagicMock(return_value="dummy error")
        with StringIO() as mock_stderr:
            with (
                patch.multiple(
                    "sys", stdin=StringIO("\n"), stdout=StringIO(), stderr=mock_stderr
                ),
                contextlib.suppress(EOFError),
            ):
                pyseed.get_input("dummy prompt", validator=validator)
            mock_stderr.seek(0)
            self.assertEqual(mock_stderr.read(), "error: dummy error\n")

    def test_get_input_reads_input_til_valid(self):
        validation_outputs = ["error", "error", "error", None]
        validator = MagicMock(side_effect=validation_outputs)

        mock_stdins = ["x", "x", "x", "hello, world"]
        with patch.multiple(
            "sys",
            stdin=StringIO("\n".join(mock_stdins)),
            stdout=StringIO(),
            stderr=StringIO(),
        ):
            inp = pyseed.get_input("", validator=validator)

        validator.assert_has_calls(
            [mock.call("x"), mock.call("x"), mock.call("x"), mock.call("hello, world")]
        )
        self.assertEqual(inp, "hello, world")

    def test_tty_stdin_is_noop_if_not_ensure_tty(self):
        mock_stdin = StringIO()
        with (
            patch("sys.stdin", mock_stdin),
            patch("pyseed.ensure_tty", False),
            pyseed.tty_stdin(),
        ):
            self.assertIs(sys.stdin, mock_stdin)

    def test_tty_stdin_is_noop_if_stdin_is_tty(self):
        mock_stdin = MagicMock()
        mock_stdin.isatty = MagicMock(return_value=True)
        with (
            patch("sys.stdin", mock_stdin),
            patch("pyseed.ensure_tty", True),
            pyseed.tty_stdin(),
        ):
            self.assertIs(sys.stdin, mock_stdin)

    @skipUnless(os.path.exists("/dev/tty"), "need /dev/tty")
    def test_tty_stdin_redirects_stdin_in_context(self):
        mock_stdin = StringIO()
        mock_tty = StringIO()
        mock_open = MagicMock(return_value=mock_tty)
        with patch("sys.stdin", mock_stdin):
            with (
                patch("pyseed.ensure_tty", True),
                patch("builtins.open", mock_open),
                pyseed.tty_stdin(),
            ):
                self.assertIs(sys.stdin, mock_tty)
            self.assertIs(sys.stdin, mock_stdin)

    def test_get_input_reads_input_within_tty_stdin_context(self):
        mock_stdin = StringIO("hello, world")

        @contextmanager
        def mock_tty_stdin():
            try:
                sys.stdin = StringIO("goodbye, world")
                yield
            finally:
                sys.stdin = mock_stdin

        with (
            patch.multiple("sys", stdin=mock_stdin, stdout=StringIO()),
            patch("pyseed.tty_stdin", mock_tty_stdin),
        ):
            inp = pyseed.get_input("")
        self.assertEqual(inp, "goodbye, world")


class TestGetYesNoInput(TestCase):
    def test_get_yes_no_input_returns_bool(self):
        for stdin_value, true_inp in zip(["yes", "no"], [True, False]):
            with self.subTest(stdin_value):
                with patch.multiple(
                    "sys", stdin=StringIO(f"{stdin_value}"), stdout=StringIO()
                ):
                    inp = pyseed.get_yes_no_input("")
                self.assertEqual(inp, true_inp)

    def test_get_yes_no_input_accepts_single_letter(self):
        for stdin_value, true_inp in zip(["y", "n"], [True, False]):
            with self.subTest(stdin_value):
                with patch.multiple(
                    "sys", stdin=StringIO(f"{stdin_value}"), stdout=StringIO()
                ):
                    inp = pyseed.get_yes_no_input("")
                self.assertEqual(inp, true_inp)

    def test_get_yes_no_input_returns_default_value(self):
        for tf in [True, False]:
            with self.subTest(tf):
                with patch.multiple("sys", stdin=StringIO("\n"), stdout=StringIO()):
                    inp = pyseed.get_yes_no_input("", default=tf)
                self.assertEqual(inp, tf)

    def test_get_yes_no_input_rejects_invalid_input(self):
        mock_stdins = ["x", "yesss", "", "yesno", "yes", "no"]
        with patch.multiple(
            "sys",
            stdin=StringIO("\n".join(mock_stdins)),
            stdout=StringIO(),
            stderr=StringIO(),
        ):
            inp = pyseed.get_yes_no_input("")
        self.assertTrue(inp)


class TestStrConfigKeySpec(TestCase):
    def assertHasAttrWithValue(self, obj, attr, value):  # noqa: N802
        self.assertTrue(hasattr(obj, attr))
        self.assertEqual(getattr(obj, attr), value)

    def setUp(self):
        self.mock_validator = MagicMock(return_value=None)
        self.mock_key = pyseed.StrConfigKeySpec(
            "dummy_param",
            description="dummy help",
            default="dummy default",
            validator=self.mock_validator,
        )

    def test_str_config_key_can_be_read_interactively(self):
        with StringIO() as mock_stdout:
            with patch.multiple(
                "sys", stdin=StringIO("hello, world"), stdout=mock_stdout
            ):
                val = self.mock_key.get_value_interactively()
            self.assertEqual(val, "hello, world")
            self.mock_validator.assert_called_once_with("hello, world")
            mock_stdout.seek(0)
            self.assertEqual(
                mock_stdout.read(), "dummy help [default: 'dummy default']: "
            )

    def test_str_config_key_can_be_read_from_cmdline(self):
        argparser = ArgumentParser()
        self.mock_key.add_arg_to_argparser(argparser)
        args = argparser.parse_args(["--dummy-param", "hello, world"])
        self.assertHasAttrWithValue(args, "dummy_param", "hello, world")
        self.mock_validator.assert_called_once_with("hello, world")

    def test_str_config_key_handles_single_char_names(self):
        argparser = ArgumentParser()
        mock_key = pyseed.StrConfigKeySpec("x", description="")
        mock_key.add_arg_to_argparser(argparser)
        args = argparser.parse_args(["-xhello"])
        self.assertHasAttrWithValue(args, "x", "hello")

    def test_str_config_key_uses_default_value_with_argparse(self):
        argparser = ArgumentParser()
        self.mock_key.add_arg_to_argparser(argparser)
        args = argparser.parse_args([])
        self.assertHasAttrWithValue(args, "dummy_param", "dummy default")
        self.mock_validator.assert_called_once_with("dummy default")

    def test_str_config_key_adds_required_argument_if_no_default(self):
        argparser = ArgumentParser()
        mock_key = pyseed.StrConfigKeySpec("dummy_param", description="")
        mock_key.add_arg_to_argparser(argparser)
        with patch("sys.stderr", StringIO()), self.assertRaises(SystemExit):
            argparser.parse_args([])

    def test_str_config_key_does_not_add_default_if_no_default_required(self):
        argparser = ArgumentParser()
        self.mock_key.add_arg_to_argparser(argparser, no_default_required=True)
        args = argparser.parse_args([])
        self.assertHasAttrWithValue(args, "dummy_param", None)

    def test_str_config_key_does_not_make_required_if_no_default_required(self):
        argparser = ArgumentParser()
        mock_key = pyseed.StrConfigKeySpec("dummy_param", description="")
        mock_key.add_arg_to_argparser(argparser, no_default_required=True)
        args = argparser.parse_args([])
        self.assertHasAttrWithValue(args, "dummy_param", None)

    def test_str_config_key_adds_note_about_barebones_iff_in_ignored_list(self):
        argparser = ArgumentParser(add_help=False, usage="")
        pyseed.ConfigKey.url.value.add_arg_to_argparser(argparser)
        self.assertIn("ignored in barebones mode", argparser.format_help())

        argparser = ArgumentParser(add_help=False, usage="")
        pyseed.ConfigKey.description.value.add_arg_to_argparser(argparser)
        self.assertNotIn("ignored in barebones mode", argparser.format_help())


class TestBoolConfigKeySpec(TestCase):
    def assertHasAttrWithValue(self, obj, attr, value):  # noqa: N802
        self.assertTrue(hasattr(obj, attr))
        self.assertEqual(getattr(obj, attr), value)

    def test_bool_config_key_can_be_read_interactively(self):
        mock_key = pyseed.BoolConfigKeySpec("dummy_param", description="", default=True)
        with patch.multiple("sys", stdin=StringIO("no"), stdout=StringIO()):
            inp = mock_key.get_value_interactively()
        self.assertFalse(inp)
        with patch.multiple("sys", stdin=StringIO("\n"), stdout=StringIO()):
            inp = mock_key.get_value_interactively()
        self.assertTrue(inp)

    def test_bool_config_key_adds_set_false_argument_for_true_default(self):
        mock_key = pyseed.BoolConfigKeySpec("dummy_param", description="", default=True)
        argparser = ArgumentParser()
        mock_key.add_arg_to_argparser(argparser)
        args = argparser.parse_args(["--no-dummy-param"])
        self.assertHasAttrWithValue(args, "dummy_param", False)
        args = argparser.parse_args([])
        self.assertHasAttrWithValue(args, "dummy_param", True)

    def test_bool_config_key_adds_set_true_argument_for_false_default(self):
        mock_key = pyseed.BoolConfigKeySpec(
            "dummy_param", description="", default=False
        )
        argparser = ArgumentParser()
        mock_key.add_arg_to_argparser(argparser)
        args = argparser.parse_args(["--dummy-param"])
        self.assertHasAttrWithValue(args, "dummy_param", True)
        args = argparser.parse_args([])
        self.assertHasAttrWithValue(args, "dummy_param", False)

    def test_bool_config_key_adds_mutex_args_for_no_default(self):
        mock_key = pyseed.BoolConfigKeySpec("dummy_param", description="")
        argparser = ArgumentParser(exit_on_error=False)
        mock_key.add_arg_to_argparser(argparser)
        args = argparser.parse_args(["--dummy-param"])
        self.assertHasAttrWithValue(args, "dummy_param", True)
        args = argparser.parse_args(["--no-dummy-param"])
        self.assertHasAttrWithValue(args, "dummy_param", False)
        with self.assertRaises(ArgumentError):
            argparser.parse_args(["--dummy-param", "--no-dummy-param"])

    def test_bool_config_key_returns_none_with_no_default_required(self):
        mock_key = pyseed.BoolConfigKeySpec("dummy_param", description="")
        argparser = ArgumentParser()
        mock_key.add_arg_to_argparser(argparser, no_default_required=True)
        args = argparser.parse_args([])
        self.assertHasAttrWithValue(args, "dummy_param", None)

    def test_bool_config_key_adds_note_about_barebones_iff_in_ignored_list(self):
        argparser = ArgumentParser(add_help=False, usage="")
        pyseed.ConfigKey.no_github.value.add_arg_to_argparser(argparser)
        self.assertIn("ignored in barebones mode", argparser.format_help())

        argparser = ArgumentParser(add_help=False, usage="")
        pyseed.ConfigKey.add_deps.value.add_arg_to_argparser(argparser)
        self.assertNotIn("ignored in barebones mode", argparser.format_help())


class TestGetConf(TestCase):
    def setUp(self):
        class DummyConfigKey(Enum):
            dummy_str_key = pyseed.StrConfigKeySpec("dummy_str_key", description="")
            dummy_bool_key = pyseed.BoolConfigKeySpec("dummy_bool_key", description="")

        self.DummyConfigKey = DummyConfigKey

    def _get_patched_argparser(self, argv: list[str]) -> ArgumentParser:
        mock_argparser = ArgumentParser(exit_on_error=False)
        orig_parse_args = mock_argparser.parse_args
        new_parse_args = lambda *_, **__: orig_parse_args(argv)  # noqa: E731
        setattr(mock_argparser, "parse_args", new_parse_args)  # noqa
        return mock_argparser

    def test_get_conf_uses_interactive_mode_with_no_args(self):
        mock_stdin = StringIO("hello, world\nyes")
        with (
            patch("pyseed.ConfigKey", self.DummyConfigKey),
            patch("pyseed.sys.argv", []),
            patch.multiple("sys", stdin=mock_stdin, stdout=StringIO()),
        ):
            config_mode, _ = pyseed.get_conf()
        self.assertEqual(config_mode, pyseed.ConfigMode.interactive)

    def test_get_conf_uses_non_interactive_mode_with_args(self):
        argv = ["--dummy-str-key", "hello, world", "--dummy-bool-key"]
        mock_argparser = self._get_patched_argparser(argv)
        with (
            patch("pyseed.ConfigKey", self.DummyConfigKey),
            patch("pyseed.ArgumentParser", MagicMock(return_value=mock_argparser)),
            patch("pyseed.sys.argv", argv),
            patch.multiple("sys", stdin=StringIO(), stdout=StringIO()),
        ):
            config_mode, _ = pyseed.get_conf()
        self.assertEqual(config_mode, pyseed.ConfigMode.non_interactive)

    def test_get_conf_interactively_returns_dict_with_config_keys(self):
        mock_stdin = StringIO("hello, world\nyes")
        with (
            patch("pyseed.ConfigKey", self.DummyConfigKey),
            patch.multiple("sys", stdin=mock_stdin, stdout=StringIO()),
        ):
            config = pyseed.get_conf_interactively()
        self.assertDictEqual(
            config,
            {
                self.DummyConfigKey.dummy_str_key: "hello, world",
                self.DummyConfigKey.dummy_bool_key: True,
            },
        )

    def test_get_conf_interactively_ignores_keys_in_base_config(self):
        base_config = {
            self.DummyConfigKey.dummy_str_key: "dummy default",
            self.DummyConfigKey.dummy_bool_key: False,
        }
        with StringIO() as mock_stdout:
            with (
                patch("pyseed.ConfigKey", self.DummyConfigKey),
                patch.multiple("sys", stdin=StringIO("\n"), stdout=mock_stdout),
            ):
                config = pyseed.get_conf_interactively(base_config)  # type: ignore
            mock_stdout.seek(0)
            self.assertEqual(mock_stdout.read().strip(), "")
            self.assertDictEqual(config, base_config)

    def test_get_conf_interactively_updates_default_for_main_pkg_name(self):
        class DummyConfigKey(Enum):
            project = pyseed.StrConfigKeySpec("project", description="")
            main_pkg = pyseed.StrConfigKeySpec(
                "main_pkg", description="", default="not_this"
            )

        with (
            patch("pyseed.ConfigKey", DummyConfigKey),
            patch.multiple(
                "sys", stdin=StringIO("project-name\n\n"), stdout=StringIO()
            ),
        ):
            config = pyseed.get_conf_interactively()
        self.assertDictEqual(
            config,
            {
                DummyConfigKey.project: "project-name",
                DummyConfigKey.main_pkg: "project_name",
            },
        )

    def test_get_conf_skips_barebones_ignored_keys(self):
        class DummyConfigKey(Enum):
            barebones = pyseed.BoolConfigKeySpec("barebones", description="")
            dummy_str_key = pyseed.StrConfigKeySpec("dummy_str_key", description="")
            dummy_bool_key = pyseed.BoolConfigKeySpec("dummy_bool_key", description="")

        for barebones in ["yes", "no"]:
            with (
                patch.multiple(
                    "pyseed",
                    ConfigKey=DummyConfigKey,
                    BAREBONES_MODE_IGNORED_CONFIG_KEYS=[DummyConfigKey.dummy_str_key],
                ),
                patch.multiple(
                    "sys", stdin=StringIO(f"{barebones}\nyes\nyes\n"), stdout=StringIO()
                ),
            ):
                config = pyseed.get_conf_interactively()
            target_dict = {
                DummyConfigKey.barebones: barebones == "yes",
                DummyConfigKey.dummy_bool_key: True,
            }
            if barebones == "no":
                target_dict[DummyConfigKey.dummy_str_key] = "yes"
            with self.subTest(barebones=barebones):
                self.assertDictEqual(config, target_dict)

    def test_parse_cmdline_args_returns_dict_with_config_keys(self):
        argv = ["--dummy-str-key", "hello, world", "--no-dummy-bool-key"]
        mock_argparser = self._get_patched_argparser(argv)
        with (
            patch("sys.argv", argv),
            patch("pyseed.ConfigKey", self.DummyConfigKey),
            patch("pyseed.ArgumentParser", MagicMock(return_value=mock_argparser)),
        ):
            config_mode, config = pyseed.parse_cmdline_args()
        self.assertEqual(config_mode, pyseed.ConfigMode.non_interactive)
        self.assertDictEqual(
            config,
            {
                self.DummyConfigKey.dummy_str_key: "hello, world",
                self.DummyConfigKey.dummy_bool_key: False,
            },
        )

    def test_parse_cmdline_args_detects_interactive_mode_on_minus_i_arg(self):
        for iarg in ["-i", "-si", "-is", "--interactive"]:
            with self.subTest(iarg):
                with (
                    patch("pyseed.ConfigKey", self.DummyConfigKey),
                    patch("pyseed.sys.argv", [iarg, "--no-dummy-bool-key"]),
                    patch("sys.stdout", StringIO()),
                ):
                    config_mode, config = pyseed.parse_cmdline_args()
                self.assertEqual(config_mode, pyseed.ConfigMode.interactive)
                self.assertDictEqual(
                    config, {self.DummyConfigKey.dummy_bool_key: False}
                )

    def test_get_conf_combines_cmdline_and_interactive_config(self):
        with (
            patch("pyseed.ConfigKey", self.DummyConfigKey),
            patch("pyseed.sys.argv", ["-i", "--no-dummy-bool-key"]),
            patch.multiple("sys", stdin=StringIO("hello, world"), stdout=StringIO()),
        ):
            _, config = pyseed.get_conf()
        self.assertDictEqual(
            config,
            {
                self.DummyConfigKey.dummy_bool_key: False,
                self.DummyConfigKey.dummy_str_key: "hello, world",
            },
        )

    def test_get_conf_sets_main_pkg_if_not_provided(self):
        class DummyConfigKey(Enum):
            project = pyseed.StrConfigKeySpec("project", description="")
            main_pkg = pyseed.StrConfigKeySpec("main_pkg", description="")

        with (
            patch("pyseed.ConfigKey", DummyConfigKey),
            patch("pyseed.sys.argv", []),
            patch.multiple(
                "sys", stdin=StringIO("project-name\n\n"), stdout=StringIO()
            ),
        ):
            _, config = pyseed.get_conf()
        self.assertDictEqual(
            config,
            {
                DummyConfigKey.project: "project-name",
                DummyConfigKey.main_pkg: "project_name",
            },
        )


@skipUnless(
    os.environ.get("GITHUB_TOKEN"),
    "need GitHub token in environment variable `GITHUB_TOKEN`",
)
class TestGitHubAPI(TestCase):
    def setUp(self):
        self.github_api = pyseed.GitHubAPI(os.environ["GITHUB_TOKEN"])

    def test_github_api_call_gets_repo(self):
        api_response = self.github_api.call(f"repos/{GH_USER}/{GH_REPO}")
        self.assertEqual(api_response.get("full_name"), f"{GH_USER}/{GH_REPO}")

    def test_github_api_setup_secrets_manager_installs_uninstalls_nacl(self):
        for do_uninstall in [True, False]:
            with self.subTest(do_uninstall), inside_temp_poetry_dir():

                def get_pip_list() -> str:
                    _pdone = pyseed.vrun(
                        ["poetry", "run", "pip", "list", "--require-virtualenv"],
                        capture_output=True,
                    )
                    return _pdone.stdout.lower()

                self.assertNotIn("pynacl", get_pip_list())
                with self.github_api.setup_secrets_manager() as secrets_manager:
                    self.assertIn("pynacl", get_pip_list())
                    secrets_manager.do_uninstall = do_uninstall

                pip_list = get_pip_list()
                if do_uninstall:
                    self.assertNotIn("pynacl", pip_list)
                else:
                    self.assertIn("pynacl", pip_list)

    def test_github_api_secrets_manager_uploads_secret_to_repo(self):
        secret_name = "TEST_SECRET"
        with (
            inside_temp_poetry_dir(),
            self.github_api.setup_secrets_manager() as secrets_manager,
        ):
            secrets_manager.upload_actions_secret(
                GH_USER, GH_REPO, secret_name, "helloworld"
            )

        get_secret_reponse = self.github_api.call(
            f"repos/{GH_USER}/{GH_REPO}/actions/secrets/{secret_name}"
        )
        self.assertEqual(get_secret_reponse.get("name"), secret_name)

    @skipIf(not HAVE_NACL, "`nacl` must be installed to test secret encryption")
    def test_github_api_secrets_manager_produces_correct_encryption(self):
        b64_encoder = nacl.encoding.Base64Encoder()  # type: ignore
        private_key = nacl.public.PrivateKey.generate()  # type: ignore
        public_key = private_key.public_key
        public_key_b64 = public_key.encode(b64_encoder).decode("utf-8")

        secret = "helloworld"
        with (
            inside_temp_poetry_dir(),
            self.github_api.setup_secrets_manager() as secrets_manager,
        ):
            secret_encrypted_b64 = secrets_manager.encrypt(public_key_b64, secret)

        private_key_sealed_box = nacl.public.SealedBox(private_key)  # type: ignore
        secret_decrypted = private_key_sealed_box.decrypt(
            secret_encrypted_b64, b64_encoder
        ).decode("utf-8")

        self.assertEqual(secret, secret_decrypted)
        secret_decrypted = private_key_sealed_box.decrypt(
            secret_encrypted_b64, b64_encoder
        ).decode("utf-8")

        self.assertEqual(secret, secret_decrypted)
        self.assertEqual(secret, secret_decrypted)


class _BaseTestCreateProject(TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.project_name = Path(self.tempdir.name).stem
        self.config: dict[pyseed.ConfigKey, Any] = {
            pyseed.ConfigKey.barebones: False,
            pyseed.ConfigKey.project: Path(self.tempdir.name) / self.project_name,
            pyseed.ConfigKey.description: "test description",
            pyseed.ConfigKey.url: "http://test.example.com",
            pyseed.ConfigKey.main_pkg: "test_project",
            pyseed.ConfigKey.add_mit_license: True,
            pyseed.ConfigKey.authors: (
                "A Person <aperson@example.com>, B Person <bperson@example.com>"
            ),
            pyseed.ConfigKey.min_py_version: "3.9",
            pyseed.ConfigKey.max_py_version: "3.12",
            pyseed.ConfigKey.add_py_typed: True,
            pyseed.ConfigKey.update_pc_hooks_on_schedule: False,
            pyseed.ConfigKey.add_deps: "",
            pyseed.ConfigKey.add_dev_deps: "",
            pyseed.ConfigKey.no_github: False,
            pyseed.ConfigKey.no_doctests: False,
        }

    def tearDown(self):
        os.chdir(pwd_abs)
        self.tempdir.cleanup()


class TestInitProject(_BaseTestCreateProject):
    def test_init_project_writes_all_expected_files(self):
        for i, no_github in enumerate([False, True]):
            if i != 0:
                self.tearDown()
                self.setUp()

            self.config[pyseed.ConfigKey.no_github] = no_github

            pyseed.init_project(self.config)
            project_dir = Path(self.tempdir.name) / self.project_name

            self.assertTrue(project_dir.exists())
            check_exist_fnames = [
                "scripts/gen_site_usage_pages.py",
                "scripts/make_docs.py",
                "src/test_project/__init__.py",
                "src/test_project/_version.py",
                "src/test_project/py.typed",
                "tests/__init__.py",
                "tests/test_doctests.py",
                "www/theme/overrides/main.html",
                ".commitlintrc.yaml",
                ".cspell.json",
                ".editorconfig",
                ".gitattributes",
                ".gitignore",
                ".pre-commit-config.yaml",
                ".prettierignore",
                ".prettierrc.js",
                "CHANGELOG.md",
                "LICENSE.md",
                "README.md",
                "mkdocs.yml",
                "project-words.txt",
                "pyproject.toml",
            ]
            no_github_fnames = ["scripts/release_new_version.py"]
            yes_github_fnames = [
                "scripts/commit_and_tag_version.py",
                "scripts/verify_pr_commits.py",
                ".github/workflows/check-pr.yml",
                ".github/workflows/release-new-version.yml",
                ".github/workflows/create-github-release.yml",
                ".github/workflows/publish-to-pypi.yml",
                ".github/workflows/deploy-project-site.yml",
                ".github/workflows/run-tests.yml",
                ".github/workflows/update-pre-commit-hooks.yml",
            ]
            if no_github:
                check_exist_fnames.extend(no_github_fnames)
                check_noexist_fnames = yes_github_fnames
            else:
                check_exist_fnames.extend(yes_github_fnames)
                check_noexist_fnames = no_github_fnames

            for fname in check_exist_fnames:
                with self.subTest(no_github=no_github, should_exist=fname):
                    self.assertTrue((project_dir / fname).exists())
            for fname in check_noexist_fnames:
                with self.subTest(no_github=no_github, should_not_exist=fname):
                    self.assertFalse((project_dir / fname).exists())

            www_src_dir = project_dir / "www" / "src"
            for fname in ["CHANGELOG.md", "LICENSE.md"]:
                with self.subTest(no_github=no_github, should_exist=fname):
                    self.assertEqual(
                        (www_src_dir / fname).resolve(), (project_dir / fname).resolve()
                    )
            self.assertEqual(
                (www_src_dir / "index.md").resolve(),
                (project_dir / "README.md").resolve(),
            )

            scripts_dir = project_dir / "scripts"
            for fpath in scripts_dir.glob("*"):
                with self.subTest(no_github=no_github, should_exist=fpath):
                    self.assertTrue(os.access(fpath, os.X_OK))

    def test_init_project_writes_all_expected_files_in_barebones_mode(self):
        self.config[pyseed.ConfigKey.barebones] = True
        for key in pyseed.BAREBONES_MODE_IGNORED_CONFIG_KEYS:
            del self.config[key]

        pyseed.init_project(self.config)
        project_dir = Path(self.tempdir.name) / self.project_name

        self.assertTrue(project_dir.exists())
        for fname in [
            "test_project/__init__.py",
            ".cspell.json",
            ".editorconfig",
            ".gitignore",
            ".pre-commit-config.yaml",
            "LICENSE.md",
            "README.md",
            "project-words.txt",
            "pyproject.toml",
        ]:
            with self.subTest(fname):
                self.assertTrue((project_dir / fname).exists())

        for fname in [
            ".github",
            "scripts",
            "src",
            "tests",
            "www",
            ".commitlintrc.yaml",
            ".gitattributes",
            ".prettierignore",
            ".prettierrc.js",
            "CHANGELOG.md",
            "mkdocs.yml",
        ]:
            with self.subTest(fname):
                self.assertFalse((project_dir / fname).exists())

    def test_init_project_does_not_add_suppressed_files(self):
        for i, barebones in enumerate([False, True]):
            with self.subTest(barebones=barebones):
                if i == 1:
                    self.tearDown()
                    self.setUp()
                self.config[pyseed.ConfigKey.barebones] = barebones
                self.config[pyseed.ConfigKey.add_mit_license] = False
                self.config[pyseed.ConfigKey.add_py_typed] = False
                self.config[pyseed.ConfigKey.no_doctests] = True

                if barebones:
                    for key in pyseed.BAREBONES_MODE_IGNORED_CONFIG_KEYS:
                        del self.config[key]

                pyseed.init_project(self.config)

                project_dir = Path(self.tempdir.name) / self.project_name
                self.assertTrue(project_dir.exists())
                self.assertFalse((project_dir / "src/test_project/py.typed").exists())

                license_text = (project_dir / "LICENSE.md").read_text().strip()
                self.assertEqual(license_text, "")

                self.assertFalse((project_dir / "tests" / "test_doctests.py").exists())

    @skipUnless(
        HAVE_TOML and HAVE_YAML, "need tomllib and pyyaml to test template renders"
    )
    def test_init_project_renders_templates_correctly(self):
        self.config[pyseed.ConfigKey.description] = '{hello}\n"world"'
        self.config[pyseed.ConfigKey.authors] = (
            "So'me \"One <someone@example.com>, No Email"
        )
        self.config[pyseed.ConfigKey.update_pc_hooks_on_schedule] = True

        pyseed.init_project(self.config)
        project_dir = Path(self.tempdir.name) / self.project_name

        pyproject_path = project_dir / "pyproject.toml"
        with pyproject_path.open("rb") as f:
            pyproject_toml = tomllib.load(f)
        poetry_data = pyproject_toml["tool"]["poetry"]
        self.assertDictEqual(
            poetry_data,
            {
                "name": self.project_name,
                "description": '{hello}\n"world"',
                "version": "0.0.0",
                "authors": ["So'me \"One <someone@example.com>", "No Email"],
                "license": "MIT",
                "readme": "README.md",
                "packages": [{"include": "test_project", "from": "src"}],
                "include": [
                    {"path": "tests", "format": "sdist"},
                    {"path": "docs", "format": "sdist"},
                    {"path": "CHANGELOG.md", "format": "sdist"},
                ],
                "dependencies": {"python": "^3.9"},
                "extras": {},
                "group": {"dev": {"dependencies": {}}},
            },
        )

        update_hooks_workflow_path = (
            project_dir / ".github" / "workflows" / "update-pre-commit-hooks.yml"
        )
        with update_hooks_workflow_path.open("rb") as f:
            update_hooks_workflow_data = yaml.load(f, yaml.Loader)
        self.assertEqual(
            # PyYAML treats "on" as True.
            update_hooks_workflow_data[True]["schedule"],
            [{"cron": "0 0 1 * *"}],
        )

        mkdocs_cfg_path = project_dir / "mkdocs.yml"
        with mkdocs_cfg_path.open("rb") as f:
            mkdocs_cfg_data = yaml.load(f, yaml.Loader)
        self.assertEqual(mkdocs_cfg_data["site_name"], self.project_name)
        self.assertEqual(mkdocs_cfg_data["site_url"], "http://test.example.com")
        self.assertEqual(
            mkdocs_cfg_data["site_description"],
            f"Documentation for '{self.project_name}'.",
        )
        self.assertEqual(mkdocs_cfg_data["site_author"], "So'me \"One, No Email")
        self.assertEqual(
            mkdocs_cfg_data["copyright"], "Copyright (c) So'me \"One, No Email"
        )

        run_tests_workflow_path = (
            project_dir / ".github" / "workflows" / "run-tests.yml"
        )
        with run_tests_workflow_path.open("rb") as f:
            run_tests_workflow_data = yaml.load(f, yaml.Loader)
        self.assertEqual(
            run_tests_workflow_data["jobs"]["main"]["strategy"]["matrix"][
                "python-version"
            ],
            ["3.9", "3.10", "3.11", "3.12"],
        )
        self.assertEqual(
            run_tests_workflow_data["jobs"]["main"]["strategy"]["fail-fast"],
            "${{ inputs.fail-fast }}",
        )
        self.assertEqual(
            run_tests_workflow_data["jobs"]["main"]["runs-on"], "${{ matrix.os }}"
        )
        self.assertEqual(
            run_tests_workflow_data["jobs"]["main"]["steps"][1]["with"][
                "python-version"
            ],
            "${{ matrix.python-version }}",
        )

        license_path = project_dir / "LICENSE.md"
        license_data = license_path.read_text()
        self.assertTrue(
            license_data.startswith(
                "# MIT License\n\nCopyright (c) So'me \"One, No Email"
            )
        )

        readme_path = project_dir / "README.md"
        readme_data = readme_path.read_text()
        self.assertEqual(readme_data, f'# {self.project_name}\n\n{{hello}}\n"world"\n')

    @skipUnless(
        HAVE_TOML and HAVE_YAML, "need tomllib and pyyaml to test template renders"
    )
    def test_init_project_renders_templates_correctly_in_barebones_mode(self):
        self.config[pyseed.ConfigKey.barebones] = True
        self.config[pyseed.ConfigKey.description] = '{hello}\n"world"'
        self.config[pyseed.ConfigKey.authors] = (
            "So'me \"One <someone@example.com>, No Email"
        )

        for key in pyseed.BAREBONES_MODE_IGNORED_CONFIG_KEYS:
            del self.config[key]

        pyseed.init_project(self.config)
        project_dir = Path(self.tempdir.name) / self.project_name

        pyproject_path = project_dir / "pyproject.toml"
        with pyproject_path.open("rb") as f:
            pyproject_toml = tomllib.load(f)
        poetry_data = pyproject_toml["tool"]["poetry"]
        self.assertDictEqual(
            poetry_data,
            {
                "package-mode": False,
                "dependencies": {"python": "^3.9"},
                "group": {"dev": {"dependencies": {}}},
            },
        )

    @skipUnless(HAVE_YAML, "need pyyaml to test yaml renders")
    def test_init_project_does_not_add_schedule_to_hooks_workflow_if_disabled(self):
        pyseed.init_project(self.config)
        project_dir = Path(self.tempdir.name) / self.project_name

        update_hooks_workflow_path = (
            project_dir / ".github" / "workflows" / "update-pre-commit-hooks.yml"
        )
        with update_hooks_workflow_path.open("rb") as f:
            update_hooks_workflow_data = yaml.load(f, yaml.Loader)
        self.assertNotIn("schedule", update_hooks_workflow_data[True])


@skipUnless(
    os.environ.get("PYSEED_TEST_CREATE_PROJECT"),
    "must be enabled explicitly by setting `PYSEED_TEST_CREATE_PROJECT`",
)
class TestCreateProject(_BaseTestCreateProject):
    def test_create_project_runs_without_error(self):
        for i, no_github in enumerate([False, True]):
            if i != 0:
                self.tearDown()
                self.setUp()

            self.config[pyseed.ConfigKey.no_github] = no_github
            self.config[pyseed.ConfigKey.add_deps] = "requests;flask>=2.0,<3.0"
            self.config[pyseed.ConfigKey.add_dev_deps] = "black"
            pyseed.init_project(self.config)
            pyseed.create_project(self.config)
            pdone = pyseed.vrun(
                ["git", "log", "--max-count=1", "--pretty=format:%s"],
                capture_output=True,
            )
            with self.subTest(no_github=no_github):
                self.assertEqual(pdone.stdout.strip(), "chore: initial commit")
            pdone = pyseed.vrun(
                ["poetry", "run", "pip", "list", "--format", "freeze"],
                capture_output=True,
            )
            installed_pkgs = {
                line.split("==")[0].lower() for line in pdone.stdout.splitlines()
            }
            for pkg in ["requests", "flask", "black"]:
                with self.subTest(no_github=no_github, package=pkg):
                    self.assertIn(pkg, installed_pkgs)

            project_dir = Path(self.tempdir.name) / self.project_name
            (project_dir / "src" / "test_project" / "foo.py").write_text(
                textwrap.dedent('''
                def foo(x, y):
                    """Do foo.

                    Examples:
                        >>> from test_project.foo import foo
                        >>> foo(1, 2)
                        3

                    """
                    return x + y
                ''')
            )
            test_doctests_path = project_dir / "tests" / "test_doctests.py"
            test_doctests_py = test_doctests_path.read_text()
            test_doctests_path.write_text(
                re.sub(
                    r"DOCTEST_MODULES = .*\n",
                    "DOCTEST_MODULES = {test_project: ['foo.py']}\n",
                    test_doctests_py,
                )
            )

            pdone = pyseed.vrun(["poetry", "run", "python", "-m", "unittest"])
            self.assertEqual(pdone.returncode, 0)

    def test_create_project_runs_without_error_in_barebones_mode(self):
        self.config[pyseed.ConfigKey.barebones] = True
        for key in pyseed.BAREBONES_MODE_IGNORED_CONFIG_KEYS:
            del self.config[key]
        pyseed.init_project(self.config)
        pyseed.create_project(self.config)
        pdone = pyseed.vrun(
            ["git", "log", "--max-count=1", "--pretty=format:%s"], capture_output=True
        )
        self.assertEqual(pdone.stdout.strip(), "Initial commit")


@skipUnless(
    os.environ.get("PYSEED_TEST_SETUP_GITHUB"),
    "must be enabled explicitly by setting `PYSEED_TEST_SETUP_GITHUB`",
)
class TestSetupGitHub(_BaseTestCreateProject):
    def setUp(self) -> None:
        super().setUp()
        self.github_api = pyseed.GitHubAPI(os.environ["GITHUB_TOKEN"])

    def tearDown(self) -> None:
        super().tearDown()
        self.github_api.call(f"repos/{GH_USER}/{self.project_name}", "DELETE")

    def test_offline_release_script_pushes_to_github(self):
        self.config[pyseed.ConfigKey.no_github] = True
        pyseed.init_project(self.config)
        pyseed.create_project(self.config)
        self.assertTrue(Path(os.getcwd()).resolve(), Path(self.tempdir.name).resolve())

        repo_creation_response = self.github_api.call(
            "user/repos",
            "POST",
            {
                "name": self.project_name,
                "description": self.config[pyseed.ConfigKey.description],
                "homepage": self.config[pyseed.ConfigKey.url],
            },
        )
        try:
            repo_origin = repo_creation_response["ssh_url"]
        except KeyError:
            raise pyseed.GitHubAPI.Error(
                f"response:\n{repo_creation_response}"
            ) from None

        pyseed.vrun(["git", "remote", "add", "origin", repo_origin])
        pyseed.vrun(["git", "push", "-u", "origin", "master"])
        pyseed.vrun(
            [
                "poetry",
                "run",
                "scripts/release_new_version.py",
                "-f",
                "--no-pypi-publish",
            ]
        )

        pdone = pyseed.vrun(
            ["git", "ls-remote", "--tags", "origin"], capture_output=True, check=True
        )
        tags_data = pdone.stdout
        first_tag = tags_data.splitlines()[0].split("\t")[1]
        self.assertEqual(first_tag, "refs/tags/v1.0.0")

    def test_setup_github_runs_without_error(self):
        pyseed.init_project(self.config)
        pyseed.create_project(self.config)
        mock_getpass = MagicMock(
            side_effect=[self.github_api.gh_token, "dummy_repo_pat", "dummy_pypi_token"]
        )
        with (
            patch("pyseed.getpass", mock_getpass),
            patch.multiple(
                "sys",
                stdin=StringIO(f"no\n{GH_USER}\n{self.github_api.gh_token}\nno"),
                stdout=StringIO(),
                stderr=StringIO(),
            ),
        ):
            pyseed.setup_github(self.config)

        repo_get_data = self.github_api.call(f"repos/{GH_USER}/{self.project_name}")
        self.assertEqual(repo_get_data.get("name"), self.project_name)

        project_dir = Path(self.tempdir.name) / self.project_name
        repo_url = repo_get_data["html_url"]

        if HAVE_TOML:
            pyproject_path = project_dir / "pyproject.toml"
            with pyproject_path.open("rb") as f:
                pyproject_toml = tomllib.load(f)
            self.assertEqual(pyproject_toml["tool"]["poetry"]["repository"], repo_url)

        if HAVE_YAML:
            mkdocs_cfg_path = project_dir / "mkdocs.yml"
            with mkdocs_cfg_path.open("rb") as f:
                mkdocs_cfg_data = yaml.load(f, yaml.Loader)
            self.assertEqual(mkdocs_cfg_data["repo_url"], repo_url)


class TestMain(_BaseTestCreateProject):
    def setUp(self) -> None:
        super().setUp()
        self.mock_init_project = MagicMock()
        self.mock_create_project = MagicMock()
        self.mock_setup_github = MagicMock()

    def test_main_only_creates_project_in_non_interactive_mode(self):
        mock_get_conf = MagicMock(
            return_value=(pyseed.ConfigMode.non_interactive, self.config)
        )
        with patch.multiple(
            "pyseed",
            get_conf=mock_get_conf,
            init_project=self.mock_init_project,
            create_project=self.mock_create_project,
            setup_github=self.mock_setup_github,
        ):
            pyseed.main()
        self.mock_init_project.assert_called_once()
        self.mock_create_project.assert_called_once()
        self.mock_setup_github.assert_not_called()

    def test_main_asks_to_setup_github_in_interactive_mode(self):
        mock_get_conf = MagicMock(
            return_value=(pyseed.ConfigMode.interactive, self.config)
        )
        for yn in ["no", "yes"]:
            with self.subTest(setup_github=yn):
                mock_stdin = StringIO(initial_value=yn)
                self.mock_setup_github = MagicMock()
                with (
                    patch.multiple(
                        "pyseed",
                        get_conf=mock_get_conf,
                        init_project=self.mock_init_project,
                        create_project=self.mock_create_project,
                        setup_github=self.mock_setup_github,
                    ),
                    patch.multiple("sys", stdin=mock_stdin, stdout=StringIO()),
                ):
                    pyseed.main()
                    if yn == "no":
                        self.mock_setup_github.assert_not_called()
                    else:
                        self.mock_setup_github.assert_called_once()

    def test_main_does_not_setup_github_in_barebones_mode(self):
        self.config[pyseed.ConfigKey.barebones] = True
        mock_get_conf = MagicMock(
            return_value=(pyseed.ConfigMode.interactive, self.config)
        )
        with (
            patch.multiple(
                "pyseed",
                get_conf=mock_get_conf,
                init_project=self.mock_init_project,
                create_project=self.mock_create_project,
                setup_github=self.mock_setup_github,
            ),
            patch.multiple("sys", stdin=StringIO(initial_value="y"), stdout=StringIO()),
        ):
            pyseed.main()
            self.mock_setup_github.assert_not_called()

    def test_main_does_not_setup_github_if_no_github(self):
        self.config[pyseed.ConfigKey.no_github] = True
        mock_get_conf = MagicMock(
            return_value=(pyseed.ConfigMode.interactive, self.config)
        )
        with (
            patch.multiple(
                "pyseed",
                get_conf=mock_get_conf,
                init_project=self.mock_init_project,
                create_project=self.mock_create_project,
                setup_github=self.mock_setup_github,
            ),
            patch.multiple("sys", stdin=StringIO(initial_value="y"), stdout=StringIO()),
        ):
            pyseed.main()
            self.mock_setup_github.assert_not_called()

    def test_main_does_not_clean_up_in_non_interactive_mode(self):
        self.project_path = Path(self.tempdir.name) / self.project_name
        mock_get_conf = MagicMock(
            return_value=(pyseed.ConfigMode.non_interactive, self.config)
        )
        mock_stderr = StringIO()

        def mock_create_project_wrapper(_):
            self.mock_create_project()
            self.project_path.mkdir()
            raise OSError("mock error")

        with (
            patch.multiple(
                "pyseed",
                get_conf=mock_get_conf,
                init_project=self.mock_init_project,
                create_project=mock_create_project_wrapper,
                setup_github=self.mock_setup_github,
            ),
            patch.multiple("sys", stdout=StringIO(), stderr=mock_stderr),
        ):
            with self.assertRaises(SystemExit):
                pyseed.main()
            self.mock_init_project.assert_called_once()
            self.mock_create_project.assert_called_once()
            self.assertTrue(self.project_path.exists())
            self.mock_setup_github.assert_not_called()
            mock_stderr.seek(0)
            self.assertEqual(mock_stderr.read(), "mock error\n")

    def test_main_asks_to_clean_up_in_interactive_mode_on_create_error(self):
        for yn in ["no", "yes"]:
            self.project_name = f"test_project_{yn}"
            self.project_path = Path(self.tempdir.name) / self.project_name
            self.config[pyseed.ConfigKey.project] = self.project_path
            mock_get_conf = MagicMock(
                return_value=(pyseed.ConfigMode.interactive, self.config)
            )
            mock_stdin = StringIO(initial_value=yn)
            mock_stderr = StringIO()

            def mock_create_project_wrapper(_):
                self.mock_create_project()
                self.project_path.mkdir()
                raise OSError("mock error")

            with (
                patch.multiple(
                    "pyseed",
                    get_conf=mock_get_conf,
                    init_project=self.mock_init_project,
                    create_project=mock_create_project_wrapper,
                    setup_github=self.mock_setup_github,
                ),
                patch.multiple(
                    "sys", stdin=mock_stdin, stdout=StringIO(), stderr=mock_stderr
                ),
            ):
                with self.assertRaises(SystemExit):
                    pyseed.main()
                self.mock_create_project.assert_called_once()
                self.assertEqual(self.project_path.exists(), yn == "no")
                self.mock_setup_github.assert_not_called()
                self.mock_create_project.reset_mock()
                mock_stderr.seek(0)
                self.assertEqual(mock_stderr.read(), "mock error\n")

    def test_main_does_not_clean_up_if_setup_github_error(self):
        self.project_path = Path(self.tempdir.name) / self.project_name
        self.config[pyseed.ConfigKey.project] = self.project_path
        mock_get_conf = MagicMock(
            return_value=(pyseed.ConfigMode.interactive, self.config)
        )
        mock_stdin = StringIO(initial_value="yes")
        mock_stderr = StringIO()

        def mock_create_project_wrapper(_):
            self.mock_create_project()
            self.project_path.mkdir()

        def mock_setup_github_wrapper(_):
            self.mock_setup_github()
            raise OSError("mock error")

        with (
            patch.multiple(
                "pyseed",
                get_conf=mock_get_conf,
                init_project=self.mock_init_project,
                create_project=mock_create_project_wrapper,
                setup_github=mock_setup_github_wrapper,
            ),
            patch.multiple(
                "sys", stdin=mock_stdin, stdout=StringIO(), stderr=mock_stderr
            ),
        ):
            with self.assertRaises(SystemExit):
                pyseed.main()
            self.mock_create_project.assert_called_once()
            self.mock_setup_github.assert_called_once()
            self.assertTrue(self.project_path.exists())
            mock_stderr.seek(0)
            self.assertEqual(mock_stderr.read(), "mock error\n")
