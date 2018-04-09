"""Launch and control kernels using asyncio.
"""
import asyncio


@asyncio.coroutine
def shutdown(client, manager, wait_time=5.0):
    """Shutdown a kernel using a client and a manager.

    Attempts a clean shutdown by sending a shutdown message. If the kernel
    hasn't exited in wait_time seconds, it will be killed. Set wait_time=None
    to wait indefinitely.
    """
    client.shutdown()
    if (yield from manager.wait(wait_time)):
        # OK, we've waited long enough.
        manager.log.debug("Kernel is taking too long to finish, killing")
        manager.kill()
    manager.cleanup()



