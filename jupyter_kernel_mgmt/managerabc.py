from abc import ABCMeta, abstractmethod
import asyncio
import six


class KernelManagerABC(six.with_metaclass(ABCMeta, object)):
    """
    Abstract base class from which all KernelManager classes are derived.
    """

    kernel_id = None  # Subclass should set kernel_id during initialization

    @abstractmethod
    async def is_alive(self):
        """
        Check whether the kernel is currently alive (e.g. the process exists)
        """
        pass

    @abstractmethod
    async def wait(self):
        """
        Wait for the kernel process to exit.

        Returns True if the kernel is still alive after waiting, False if it
        exited (like is_alive()).
        """
        pass

    @abstractmethod
    async def signal(self, signum):
        """
        Send a signal to the kernel."""
        pass

    @abstractmethod
    async def interrupt(self):
        """
        Interrupt the kernel by sending it a signal or similar event

        Kernels can request to get interrupts as messages rather than signals.
        The manager is *not* expected to handle this.
        :meth:`.KernelClient.interrupt` should send an interrupt_request or
        call this method as appropriate.
        """
        pass

    @abstractmethod
    async def kill(self):
        """
        Forcibly terminate the kernel.

        This method may be used to dispose of a kernel that won't shut down.
        Working kernels should usually be shut down by sending shutdown_request
        from a client and giving it some time to clean up.
        """
        pass

    async def cleanup(self):
        """
        Clean up any resources, such as files created by the manager.
        """
        pass
