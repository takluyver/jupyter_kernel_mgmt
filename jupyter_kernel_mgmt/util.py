"""General utility methods"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import asyncio
import concurrent.futures
import inspect


def inherit_docstring(cls):
    def decorator(func):
        doc = getattr(cls, func.__name__).__doc__
        func.__doc__ = doc
        return func
    return decorator


def maybe_future(obj):
    """Like tornado's deprecated gen.maybe_future
    but more compatible with asyncio for recent versions
    of tornado
    """
    if inspect.isawaitable(obj):
        return asyncio.ensure_future(obj)
    elif isinstance(obj, concurrent.futures.Future):
        return asyncio.wrap_future(obj)
    else:
        # not awaitable, wrap scalar in future
        f = asyncio.Future()
        f.set_result(obj)
        return f
