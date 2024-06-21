# shiny-pyseed

shiny-pyseed is an opinionated bootstrapper for Python projects, geared
towards fast single person development.

<!--------------------------------------------------------------------->

## Features

<!--------------------------------------------------------------------->

- [Poetry](https://python-poetry.org) is used to manage dependencies and
  virtual environments.
- [pre-commit](https://pre-commit.com) hooks are installed to automate
  housekeeping tasks (like linting and formatting).
- Documentation is generated from docstrings using [Sphinx](https://www.sphinx-doc.org),
  and spell checked with [CSpell](https://cspell.org).
- Project website is built using [MkDocs](https://www.mkdocs.org),
  and published through [GitHub Pages](https://pages.github.com).
- Releasing new versions is a one-click action.
  - Commits are required to conform to the [Conventional Commits](https://www.conventionalcommits.org)
    specification, so versions are updated automatically, and a
    changelog is generated for each release.
  - Releases are published to both GitHub and PyPI.
- A GitHub repository for the project is created and configured.
  - Branch and tag protection rules are setup.
  - All pull requests are required to pass tests.
  - Pre-commit hooks are periodically auto-updated.

<!--------------------------------------------------------------------->

## Usage

<!--------------------------------------------------------------------->

### Requirements

shiny-pyseed requires Python version 3.9 or above, and [Poetry](https://python-poetry.org).
It has been tested on Windows, macOS, and Ubuntu; instructions in this
document will be provided for a Unix-like shell, which should work on
macOS and GNU/Linux distributions.

<!--------------------------------------------------------------------->

### Creating a new project

The bootstrap script, `pyseed.py` is hosted on the project website, and
can be downloaded and executed in a single command like so:

```sh
curl -sSL https://jkoushik.me/shiny-pyseed/latest/pyseed.py | python3 -
```

Alternatively, you can download or clone the project repository and run
`dist/pyseed.py`.

**NOTE: `pyseed.py` cannot be run from inside a virtual environment, and
will exit with an error if it is.**

Both of the above options will start an interactive session to configure
and create a new project. The bootstrap process runs in two phases. In
the first phase, a local Git repository for the project is created,
dependencies are installed to a new virtual environment, and an initial
commit is created. In the second (optional) phase, a GitHub repository
is created for the project, API keys and secrets needed for releases are
uploaded, and the project is pushed.

To bootstrap a project non-interactively (for example from a script),
pass command line options to the script. For example:

```sh
curl -sSL https://jkoushik.me/shiny-pyseed/latest/pyseed.py | python3 - --path testdir/testproject
```

This will create a new project inside `testdir/testproject` using
default options. **Note that the second phase (GitHub repository
creation) is skipped in non-interactive mode.**

<!--------------------------------------------------------------------->

### Workflow for bootstrapped projects

1. Use Poetry to run commands in the project's virtual environment.
2. Follow [Google's style guide](https://google.github.io/styleguide/pyguide.html#383-functions-and-methods)
   for writing docstrings.
3. Write commit messages conforming to the [Conventional Commits](https://www.conventionalcommits.org)
   specification, and maintain a linear commit history.
4. [Trigger](https://docs.github.com/en/actions/using-workflows/manually-running-a-workflow)
   the `release-new-version` workflow to create a new release. If the
   project was created with GitHub support disabled, use `scripts/release_new_version.py`.
   Run `scripts/release_new_version.py -h` for options.
5. If working on a new clone of the repository, initialize the project
   environment by running:

   ```sh
   poetry install --all-extras
   poetry run pre-commit install
   ```

<!--------------------------------------------------------------------->

### Barebones mode

shiny-pyseed can also create a barebones project which does not include:
documentation/website support, commit message enforcing, and GitHub
workflows. Also in barebones mode, the project virtual environment is
created in [non-package mode](https://python-poetry.org/docs/basic-usage/#operating-modes).

<!--------------------------------------------------------------------->

## Bootstrapping details

<!--------------------------------------------------------------------->

### Project data collection

Metadata/config for the new project is collected interactively and/or
from command line arguments. The bootstrap script has the following
modes:

1. Non-interactive mode: enabled if the script is called with command
   line arguments, but _not_ the `-i/--interactive` argument. In this
   case, all config must be provided through command line arguments, and
   the `--project` argument, which specifies the project path, is
   required.
2. Fully interactive mode: enabled if the script is called without any
   command line arguments.
3. Semi-interactive mode: enabled if the script is called with the
   `-i/--interactive` argument. Any additional command line arguments
   will become default config values, which can be overridden
   interactively.

The available configurations, and the command line arguments for
specifying them are:

1. `--barebones`: Enable barebones mode. If enabled, some of the other
   arguments will be ignored, and a barebones project will be created.
2. `--project <PATH>`: Path where the new project is created. This is
   the only required configuration.
3. `--description <DESCRIPTION>`: Project description.
4. `--url <URL>`: URL for project docs. This is needed by MkDocs; see <https://www.mkdocs.org/user-guide/configuration/#site_url>.
   It is ignored in barebones mode, which does not have MkDocs support.
5. `--pkg <PKG>`: Main Python package name. The project is initialized
   with a single package of this name. If not specified, the final
   component of the project path will be used; for example if the
   project path is `foo/bar/spam-ham`, then the default main package
   name will be `spam_ham`.
6. `--no-mit`: Do not include the MIT license.
7. `--authors <AUTHORS>`: Project authors. The project authors must be
   specified as a comma separated list of names and emails in the form
   `name <email>`. For example `Author One <aone@example.org>, Author
   Two <atwo@example.org>`. If not provided, the script will try to read
   the global Git config to get the user name and email, and use it as
   the sole author.
8. `--pym <3.MINOR.PATCH>`: Minimum supported Python version. Note that
   this cannot be lower than 3.9.
9. `--pyM <3.MINOR.PATCH>`: Maximum Python version. This only affects
   the versions used for running tests with GitHub actions. It has no
   effect in barebones mode since GitHub workflows are not included.
10. `--no-py-typed`: Do not add a `py.typed` file to the Python package.
    This file indicates that a package provides type hints.
11. `--no-pc-cron`: Do not add support for updating pre-commit hooks
    monthly through GitHub actions. Without this option, the script
    creates a periodic GitHub action that will run `pre-commit
    autoupdate` and create a pull request with the changes. It is
    ignored in barebones mode.
12. `--add-deps`: Additional Python dependencies to add to the project.
    Dependencies should be separated by ';', and follow [poetry specifications](https://python-poetry.org/docs/dependency-specification/).
13. `--add-dev-deps`: Same as `--add-deps`, except the dependencies are
    added to the 'dev' group.
14. `--no-github`: Disable GitHub support. This will omit adding any
    GitHub related files to the project, and will skip GitHub setup in
    interactive mode. It has no effect in barebones mode.

<!--------------------------------------------------------------------->

### Project folder setup

Once project information has been collected, the new project is
bootstrapped with the following operations:

1. The project folder is created.
2. Data files for the project are written.
3. A Git repository is initialized.
4. `poetry install` is called to create the project virtual environment,
   and install the project itself.
5. Dev dependencies are added: `pre-commit`, `ruff`, `mypy`, `sphinx`,
   `sphinx-markdown-builder`, `mkdocstrings`, `mkdocs-material`,
   `mkdocs-gen-files`, `mkdocs-literate-nav`, `mike`.
6. pre-commit hooks are installed and updated.
7. Prettier is used to format `pyproject.toml`.
8. Documentation is built.
9. `mkdocs build` is called to verify that the site can be built.
10. Initial Git commit is created.

<!--------------------------------------------------------------------->

### GitHub repository setup

After the project folder has been bootstrapped, shiny-pyseed can
optionally also configure a GitHub repository for the project. This is
not done in non-interactive mode, and also requires some user action.
The following operations are involved:

1. The user will need to create personal access tokens for the GitHub
   API. For information on creating a token, see
   <https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens?creating-a-token>.
   Two tokens are required:
   1. A token with 'administration:write' and 'secrets:write'
      permissions, used to create the GitHub repository. This token can
      be shared between projects, but it is highly recommended to create
      a separate token just for shiny-pyseed.
   2. A token with 'contents:write' and 'pull_requests:write'
      permissions for the project repository. This token is used for
      creating GitHub releases and publishing the website.
2. The user will also need to create a PyPI access token for uploading
   releases to PyPI. For details, see <https://pypi.org/help/#apitoken>.
3. The GitHub API is called to create a repository with the same name as
   the project.
4. `pyproject.toml` and `mkdocs.yml` are updated with the repository
   name, and the initial commit is amended.
5. The GitHub repository is added as a remote, and the initial commit is
   pushed.
6. Branch protection rules are configured for 'master' to require pull
   request reviews, and have a linear commit history.
7. Tag protection rules are setup for `v*` tags. This prevents
   non-owners from creating releases.
8. Workflow permissions are configured, to enable pull requests from
   workflows.
9. Two repository secrets are created: `REPO_PAT` containing the project
   specific GitHub API token, and `PYPI_TOKEN` containing the PyPI
   access token. **Note that if GitHub repository configuration is
   skipped, and a repository is created manually, these secrets must be
   created for the release action to work.**

<!--------------------------------------------------------------------->

## Feature details

<!--------------------------------------------------------------------->

This section describes the full set of features in a shiny-pyseed
project. For demonstration, a demo project will be used, created with
default options, to a folder named `testproject`, which will look like
this:

<!-- cSpell: disable -->

```
./
├── docs/
│   ├── index.md
│   └── testproject.md
├── .github/
│   └── workflows/
│       ├── check-pr.yml
│       ├── release-new-version.yml
│       ├── run-tests.yml
│       └── update-pre-commit-hooks.yml
├── scripts/
│   ├── commit_and_tag_version.py*
│   ├── gen_site_usage_pages.py*
│   ├── make_docs.py*
│   └── verify_pr_commits.py*
├── src/
│   └── testproject/
│       ├── __init__.py
│       ├── _version.py
│       └── py.typed
├── tests/
│   └── __init__.py
├── www/
│   ├── src/
│   │   ├── CHANGELOG.md -> ../../CHANGELOG.md
│   │   ├── index.md -> ../../README.md
│   │   └── LICENSE.md -> ../../LICENSE.md
│   └── theme/
│       └── overrides/
│           └── main.html
├── CHANGELOG.md
├── .commitlintrc.yaml
├── .cspell.json
├── .editorconfig
├── .gitattributes
├── .gitignore
├── LICENSE.md
├── mkdocs.yml
├── poetry.lock
├── .pre-commit-config.yaml
├── .prettierignore
├── .prettierrc.js
├── project-words.txt
├── pyproject.toml
└── README.md
```

<!-- cSpell: enable -->

We will now look into the various components.

### Poetry

shiny-pyseed uses Poetry to manage dependencies and virtual
environments. A virtual environment is created as part of the project
bootstrap process. See <https://python-poetry.org/docs/managing-environments>
for details on how to manage the environment creation. Use `poetry run`
to run commands inside the created environment.

The `packages` key inside `pyproject.toml` should contain all the
packages for the project. Initially, this will contain the main package
created during bootstrap. **Additional packages must be added to this
list.**

#### Versioning

[poetry-dynamic-versioning](https://github.com/mtkennerly/poetry-dynamic-versioning)
is used to automatically manage the project version using Git tags. On
build, the latest version tag will be written to
`src/<PACKAGE>/_version.py`. The version can be accessed through
`__version__`, i.e., you can do `from <PACKAGE> import __version__`.

#### Packaging type information

By default, shiny-pyseed adds an empty file named `py.typed` to the main
package, which indicates that the package provides type hints. If you do
not intend to support type checking, remove this file. For more, see
<https://typing.readthedocs.io/en/latest/spec/distributing.html#packaging-type-information>.

<!--------------------------------------------------------------------->

### Housekeeping

[Ruff](https://docs.astral.sh/ruff/) is used for formatting and linting
Python files, and is configured through `pyproject.toml`. See
`[tool.ruff]` and its sub-sections.

[mypy](https://mypy.readthedocs.io/en/stable/) is used for type
checking. Its settings are in the `[tool.mypy]` section of
`pyproject.toml`.

[Prettier](https://prettier.io) is used to format all non-Python files.
Default settings are used, and the config file, `.prettierrc.js` is only
used to load an additional plugin for prettifying `toml` files.
Files to be ignored by Prettier are listed in `.prettierignore`. As a
general rule, automatically generated files should be added here.

The Conventional Commits specification is a convention for commit
messages to make them "human and machine readable". shiny-pyseed
enforces this convention through Git hooks. Commit messages are checked
using [commitlint](https://commitlint.js.org), and will need to adhere
to the rules specified in `.commitlintrc.yaml`. The rules are a slightly
modified version of [@commitlint/config-conventional](https://github.com/conventional-changelog/commitlint/tree/master/%40commitlint/config-conventional),
with lines restricted to 72 characters.

[CSell](https://cspell.org) is used to spell check documentation
(markdown files in `docs/`, and `README.md`). The config file,
`.cspell.json`, defines a custom dictionary: `project-words.txt`. Words
added to this file will be ignored by CSpell.

<!--------------------------------------------------------------------->

### Tests

shiny-pyseed uses `unittest` as the testing framework; and test files
should be put in the `tests/` directory. If you use a different testing
framework, the following files need to be modified:
`.pre-commit-config.yaml`, `.github/workflows/run-tests.yml`. Look for
lines with `poetry run python -m unittest`, and modify them as needed.

<!--------------------------------------------------------------------->

### Docs

shiny-pyseed provides support for docs in two formats. Offline docs in
markdown, built by Sphinx, and online docs, built by MkDocs. Both
formats are built automatically from docstrings in source code. So, some
conventions need to be followed to ensure proper documentation
generation. Docstrings should follow [Google's style guide](https://google.github.io/styleguide/pyguide.html#383-functions-and-methods).

Here is a detailed example:

**`src/testproject/__init__.py`**

```python
"""This is a test project."""
from ._version import __version__
```

**`src/testproject/spam.py`**

```python
"""This is the spam module."""


class Ham:
    """This is the Ham class.

    Args:
        n: Number of eggs.

    Examples:
        >>> from testproject.spam import Ham
        >>> ham = Ham(10)
        >>> print(ham.eggs())
        10 eggs

    """

    def __init__(self, n: int):
        self.n = n

    def eggs(self):
        """Display the number of eggs."""
        print(f"{self.n} eggs")
```

**`src/testproject/foo/__init__.py`**

```python
"""This is the foo subpackage."""

from ._bar import *

# Note: we have to explicitly define `__all__` since this package does
# not have a public interface.
__all__ = _bar.__all__  # type: ignore
```

**`src/testproject/foo/_bar.py`**

```python
# No docstring here since this is a private module. Its members are
# exposed directly through the foo package.
# `__all__` can be used to control which members are documented.

__all__ = ("baz",)


def nope():
    """This won't get documented.

    Since nope is not in `__all__`, it won't be documented.
    """


def baz(x: int, y: str) -> str:
    """This is the baz function.

    Args:
        x: A number.
        y: A string.

    Returns:
        A string combining the inputs.
    """
    return f"{x} and {y}"
```

#### Offline docs

To manually generate the offline docs, run `scripts/make_docs.py`. This
script should be run inside the project virtual environment.
Alternatively, `poetry run` can be used:

```sh
poetry run scripts/make_docs.py
```

Offline docs are built using
[`sphinx-apidoc`](https://www.sphinx-doc.org/en/master/man/sphinx-apidoc.html),
[`sphinx-build`](https://www.sphinx-doc.org/en/master/man/sphinx-build.html),
[`sphinx-autodoc`](https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html),
[`napoleon`](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html), and
[`sphinx-markdown-builder`](https://github.com/liran-funaro/sphinx-markdown-builder).
The table of contents is written to `docs/index.md`, and a separate doc
file is created for each package and module.

This is what the docs will look like for the sample code above:

**`docs/index.md`**

```markdown
# testproject

- [testproject package](testproject.md)
```

**`docs/testproject.md`**

```markdown
# testproject package

This is a test project.

## Subpackages

- [testproject.foo package](testproject.foo.md)

## Submodules

- [testproject.spam module](testproject.spam.md)
```

**`docs/testproject.spam.md`**

````markdown
# testproject.spam module

This is the spam module.

### _class_ testproject.spam.Ham(n)

Bases: `object`

This is the Ham class.

- **Parameters**

  **n** (_int_) – Number of eggs.

### Examples

```python
>>> from testproject.spam import Ham
>>> ham = Ham(10)
>>> print(ham.eggs())
10 eggs
```

#### eggs()

Display the number of eggs.
````

**`docs/testproject.foo.md`**

```markdown
# testproject.foo package

This is the foo subpackage.

### testproject.foo.baz(x, y)

This is the baz function.

- **Parameters**

  - **x** (_int_) – A number.
  - **y** (_str_) – A string.

- **Returns**

  A string combining the inputs.

- **Return type**

  str
```

#### Web docs

To locally build the web docs, run `mkdocs build`. This will build the
project site to `www/_site`, which can be served locally, for example,
using Python's builtin HTTP server.

```sh
$ poetry run python -m http.server --directory www/_site
```

The site should then be accessible on `localhost:8000`. The site for
a sample project created with shiny-pyseed can be viewed at
<https://jkoushik.me/shiny-pyseed-demo>.

Site building is configured through `mkdocs.yml`. Source files for the
documentation are generated by `scripts/gen_site_usage_pages.py`. This
script, which is called automatically by `mkdocs build`, navigates the
package structure and generates a source file for each package and
module, listing all public members. These source files are read by
[`mkdocstrings`](https://mkdocstrings.github.io), which uses docstrings
from the listed members to generate html files. Navigation is managed
using [`mkdocs-literate-nav`](https://oprypin.github.io/mkdocs-literate-nav/).

[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)
is used for theming, with support for auto light/dark modes.

shiny-pyseed uses the [mike](https://github.com/jimporter/mike) plugin
to manage documentation versioning. Each time a new major/minor release
is made, a new version of the documentation is built, and all versions
can be accessed in the project site. Patch releases will update the
corresponding minor version. Note that this feature is not available
when building the site locally.

<!--------------------------------------------------------------------->

### Pre-commit hooks

shiny-pyseed uses [pre-commit](https://pre-commit.com) to automate
various tasks, using Git hooks. These hooks are installed automatically
by the bootstrap script, and will run whenever a commit is made. If any
of the hooks return a non-zero exit code, the commit is abandoned.
Pre-commit hooks are configured in `.pre-commit-config.yaml`. The
default configuration will:

- detect simple mistakes like broken symlinks, trailing newlines, etc.
- spell check the docs
- prettify files of supported types
- format Python files
- lint and type check Python files
- run tests
- build the offline docs

<!--------------------------------------------------------------------->

### EditorConfig

shiny-pyseed comes with a simple [EditorConfig](https://editorconfig.org)
configuration file (`.editorconfig`), that configures whitespace and
line endings.

<!--------------------------------------------------------------------->

### GitHub Actions

Workflows for [GitHub Actions](https://docs.github.com/en/actions) are
provided in `.github/workflows`. Some of these workflows require
[secrets](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions),
which are created by the optional second phase of the bootstrap script.
They will need to be created manually if this phase was skipped. This
section will indicate which of the following two secrets are needed by
different workflows. `REPO_PAT` is a GitHub access token with
'contents:write' and 'pull_requests:write' premissions for the
repository, and `PYPI_TOKEN` is an access key for PyPI.

**`release-new-version.yml`**
This is the workflow for creating a new release of the project. It needs
to be [triggered manually](https://docs.github.com/en/actions/using-workflows/manually-running-a-workflow),
for example using the Actions tab on GitHub. It requires the `REPO_PAT`
and `PYPI_TOKEN` secrets.

This workflow will:

- run the test workflow (`run-tests.yml`), and check if it passes
- run pre-commit hooks on all files in the repository, and check if
  there is no error
- bump the version and update `CHANGELOG.md` using
  `scripts/commit_and_tag_version.py`, which is a wrapper around
  [commit-and-tag-version](https://github.com/absolute-version/commit-and-tag-version)
- create a GitHub release using [conventional-github-releaser](https://github.com/conventional-changelog/releaser-tools/tree/master/packages/conventional-github-releaser)
- publish the project to PyPI
- publish the project site

**`check-pr.yml`**
This workflow runs automatically on pull requests. It will call
`scripts/verify_pr_commits.py` which runs `commitlint` on all commits in
the pull request. It will also run the test workflow.

**`run-tests.yml`**
This is a template workflow called by others to run tests. It runs tests
on a matrix of operating systems (ubuntu-latest, macos-latest,
windows-latest) and Python versions (configured during bootstrap).

**`update-pre-commit-hooks.yml`**
This workflow calls `pre-commit autoupdate` to update hooks to their
latest version. If there are any changes, it will create a pull request;
this requires the `REPO_PAT` secret. By default, this workflow will run
automatically every month. This can be skipped during bootstrap;
alternatively, update or remove the `schedule` section in the workflow.
