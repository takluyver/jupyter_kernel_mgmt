"""Manage and connect to Jupyter kernels"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from ._version import __version__
from .hl import (
    start_kernel_async, start_kernel_blocking,
    run_kernel_async, run_kernel_blocking,
)
