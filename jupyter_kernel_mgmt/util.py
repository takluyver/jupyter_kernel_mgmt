"""General utility methods"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import asyncio
import sys


def inherit_docstring(cls):
    def decorator(func):
        doc = getattr(cls, func.__name__).__doc__
        func.__doc__ = doc
        return func
    return decorator


def run_sync(coro_method):
    return asyncio.get_event_loop().run_until_complete(coro_method)


def _init_asyncio_patch():
    if sys.platform.startswith("win"): # and sys.version_info >= (3, 8):
        # Windows specific event-loop policy.  Although WindowsSelectorEventLoop is the current
        # default event loop priot to Python 3.8, WindowsProactorEventLoop becomes the default
        # in Python 3.8.  However, using WindowsProactorEventLoop fails during creation of
        # IOLoopKernelClient because it doesn't implement add_reader(), while using
        # WindowsSelectorEventLoop fails during asyncio.create_subprocess_exec() because it
        # doesn't implement _make_subprocess_transport().  As a result, we need to force the use of
        # the WindowsSelectorEventLoop, and essentially make process management synchronous on Windows
        # (via use_sync_subprocess). (sigh)
        # See https://github.com/takluyver/jupyter_kernel_mgmt/issues/31
        # The following approach to this is from https://github.com/jupyter/notebook/pull/5047 by @minrk
        try:
            from asyncio import (
                WindowsProactorEventLoopPolicy,
                WindowsSelectorEventLoopPolicy,
            )
        except ImportError:
            pass
            # not affected
        else:
            if type(asyncio.get_event_loop_policy()) is WindowsProactorEventLoopPolicy:
                # WindowsProactorEventLoopPolicy is not compatible with tornado 6
                # fallback to the pre-3.8 default of Selector
                asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())
            print(asyncio.get_event_loop_policy())
