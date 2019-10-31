"""General utility methods"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import asyncio


def inherit_docstring(cls):
    def decorator(func):
        doc = getattr(cls, func.__name__).__doc__
        func.__doc__ = doc
        return func
    return decorator


def run_sync(coro_method):
    return asyncio.get_event_loop().run_until_complete(coro_method)
