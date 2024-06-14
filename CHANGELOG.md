# Changelog

All notable changes to this project will be documented in this file. See [commit-and-tag-version](https://github.com/absolute-version/commit-and-tag-version) for commit guidelines.

## [1.0.3](https://github.com/jayanthkoushik/shiny-pyseed/compare/v1.0.2...v1.0.3) (2024-06-14)


### ⚠ BREAKING CHANGES

* The option to install `typing_extensions` during
bootstrap has been removed.
* Config option for notebooks has been removed. It is no
longer possible to install `jupyter` during bootstrap.

### Features

* add barebones mode for creating simple projects ([0b63bb1](https://github.com/jayanthkoushik/shiny-pyseed/commit/0b63bb1b302aeffc76c80f3cf681643f7fb2bcd3))
* incorporate notebook formatting hook to main pre-commit config ([6188dc6](https://github.com/jayanthkoushik/shiny-pyseed/commit/6188dc6c969ee996937708959af39196e35e2412))
* make pypi publishing optional in release workflow ([796a01e](https://github.com/jayanthkoushik/shiny-pyseed/commit/796a01e4e1f816aaf1842c1a216b6cd4bdcbfd20))
* remove `typing_extensions` config ([f94d7e2](https://github.com/jayanthkoushik/shiny-pyseed/commit/f94d7e20ef29311f46722bb64431fe60a94a4dc5))
* remove unnecessary `sh` plugin for prettifier ([2927c07](https://github.com/jayanthkoushik/shiny-pyseed/commit/2927c073d1d292b4a4380471edd9fe0b53a4c0b5))


### Bug Fixes

* add code to remove trailing newlines in `make_docs.py` ([60f7f86](https://github.com/jayanthkoushik/shiny-pyseed/commit/60f7f863a75991502c21a16d1a878fce98ad1b93))
* update `gen_site_usage_pages.py` to add doc from `__init__.py` ([823bfe3](https://github.com/jayanthkoushik/shiny-pyseed/commit/823bfe36de21351fc0a54e19fdcef40229893da3))

## [1.0.2](https://github.com/jayanthkoushik/shiny-pyseed/compare/v1.0.1...v1.0.2) (2024-05-24)

## [1.0.1](https://github.com/jayanthkoushik/shiny-pyseed/compare/v1.0.0...v1.0.1) (2024-05-23)


### Bug Fixes

* handle stdin not being tty in interactive mode ([4a494d6](https://github.com/jayanthkoushik/shiny-pyseed/commit/4a494d6d4bae180ad3366b648f995ab77653601b))
