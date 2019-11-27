"""Manage and connect to Jupyter kernels"""

from ._version import __version__
from .hl import (
    start_kernel_async, start_kernel_blocking,
    run_kernel_async, run_kernel_blocking,
)
