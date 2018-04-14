from abc import ABCMeta, abstractmethod
import asyncio
import six

class KernelManagerABC(six.with_metaclass(ABCMeta, object)):
    @abstractmethod
    def is_alive(self):
        """Check whether the kernel is currently alive (e.g. the process exists)
        """
        pass

    @abstractmethod
    def wait(self, timeout):
        """Wait for the kernel process to exit.

        If timeout is a number, it is a maximum time in seconds to wait.
        timeout=None means wait indefinitely.

        Returns True if the kernel is still alive after waiting, False if it
        exited (like is_alive()).
        """
        pass

    @abstractmethod
    def signal(self, signum):
        """Send a signal to the kernel."""
        pass

    @abstractmethod
    def interrupt(self):
        """Interrupt the kernel by sending it a signal or similar event

        Kernels can request to get interrupts as messages rather than signals.
        The manager is *not* expected to handle this.
        :meth:`.KernelClient2.interrupt` should send an interrupt_request or
        call this method as appropriate.
        """
        pass

    @abstractmethod
    def kill(self):
        """Forcibly terminate the kernel.

        This method may be used to dispose of a kernel that won't shut down.
        Working kernels should usually be shut down by sending shutdown_request
        from a client and giving it some time to clean up.
        """
        pass

    def cleanup(self):
        """Clean up any resources, such as files created by the manager."""
        pass


# noinspection PyCompatibility
class AsyncManagerWrapper(KernelManagerABC):
    """Wrap a blocking KernelLauncher to be used asynchronously.

    This calls the blocking methods in the event loop's default executor.
    """
    def __init__(self, wrapped, loop=None):
        self.wrapped = wrapped
        self.loop = loop or asyncio.get_event_loop()

    def _exec(self, f, *args):
        return self.loop.run_in_executor(None, f, *args)

    @asyncio.coroutine
    def is_alive(self):
        return (yield from self._exec(self.wrapped.is_alive))

    @asyncio.coroutine
    def wait(self, timeout):
        return (yield from self._exec(self.wrapped.wait, timeout))

    @asyncio.coroutine
    def signal(self, signum):
        return (yield from self._exec(self.wrapped.signal, signum))

    @asyncio.coroutine
    def interrupt(self):
        return (yield from self._exec(self.wrapped.interrupt))

    @asyncio.coroutine
    def kill(self):
        return (yield from self._exec(self.wrapped.kill))

    @asyncio.coroutine
    def cleanup(self):
        return (yield from self._exec(self.wrapped.cleanup))
