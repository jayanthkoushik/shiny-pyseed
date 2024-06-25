from doctest import DocFileSuite

import {main_pkg}

DOCTEST_MODULES = {{{main_pkg}: []}}  # type: ignore
DOCTEST_FILES = ["../README.md"]


def load_tests(loader, tests, ignore):
    for mod, modfiles in DOCTEST_MODULES.items():
        for file in modfiles:
            tests.addTest(DocFileSuite(file, package=mod))

    for file in DOCTEST_FILES:
        tests.addTest(DocFileSuite(file))

    return tests
