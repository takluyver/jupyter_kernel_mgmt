# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from .. import localinterfaces


def test_load_ips():
    # Override the machinery that skips it if it was called before
    localinterfaces._load_ips.called = False

    # Just check this doesn't error
    localinterfaces._load_ips(suppress_exceptions=False)
