"""High-level APIs"""
from contextlib import contextmanager
from .client import IOLoopKernelClient, BlockingKernelClient
from .util import run_sync
from .discovery import KernelFinder

async def start_kernel_async(name, cwd=None, launch_params=None, finder=None):
    """Start a kernel by kernel type name, return (manager, async client)"""
    kf = finder or KernelFinder.from_entrypoints()
    conn_info, km = await kf.launch(name, cwd=cwd, launch_params=launch_params)
    kc = IOLoopKernelClient(conn_info, manager=km)
    try:
        await kc.wait_for_ready()
    except:
        await kc.shutdown_or_terminate()
        kc.close()
        raise

    return km, kc


# @asynccontextmanager decorator is new in Python 3.7, so for now we'll write
# this out as a class.
class run_kernel_async:
    """Context manager to run a kernel by kernel type name.

    Gives an async client::

        async with run_kernel_blocking("pyimport/kernel") as kc:
            await kc.execute("a = 6 * 7")
    """

    km = None
    kc = None

    def __init__(self, name, **kwargs):
        self.launch_coro = start_kernel_async(name, **kwargs)

    async def __aenter__(self):
        self.km, self.kc = await self.launch_coro
        return self.kc

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.kc.shutdown_or_terminate()
        self.kc.close()
        return False  # Don't suppress exceptions


def start_kernel_blocking(
        name, *, cwd=None, launch_params=None, finder=None, startup_timeout=60,
):
    """Start a kernel by kernel type name, return (manager, blocking client)"""
    kf = finder or KernelFinder.from_entrypoints()
    conn_info, km = run_sync(kf.launch(name, cwd=cwd, launch_params=launch_params))
    kc = BlockingKernelClient(conn_info, manager=km)
    try:
        kc.wait_for_ready(timeout=startup_timeout)
    except:
        kc.shutdown_or_terminate()
        kc.close()
        raise

    return km, kc

@contextmanager
def run_kernel_blocking(name, **kwargs):
    """Context manager to run a kernel by kernel type name.

    Gives a blocking client::

        with run_kernel_blocking("pyimport/kernel") as kc:
            kc.execute_interactive("print(6 * 7)")
    """
    km, kc = start_kernel_blocking(name, **kwargs)
    try:
        yield kc
    finally:
        kc.shutdown_or_terminate()
        kc.close()
