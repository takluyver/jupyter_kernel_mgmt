"""Base class to manage a running kernel"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from __future__ import absolute_import

import asyncio
import logging
import os
import signal
import subprocess
import sys
import uuid

log = logging.getLogger(__name__)

from traitlets.log import get_logger as get_app_logger

from ..managerabc import KernelManagerABC

# Abstract the decision on whether to use a sync popen so we
# can easily enable it on non-windows systems.  This value should
# remain True for win32 until asyncio.create_subprocess_exec works.
if sys.platform == 'win32':
    use_sync_subprocess = True
else:
    use_sync_subprocess = False

class KernelManager(KernelManagerABC):
    """Manages a single kernel in a subprocess on this host.

    Parameters
    ----------

    popen : subprocess.Popen
      The process with the started kernel
    files_to_cleanup : list of paths, optional
      Files to be cleaned up after terminating this kernel.
    win_interrupt_evt :
      On Windows, a handle to be used to interrupt the kernel.
      Not used on other platforms.
    """
    def __init__(self, popen, files_to_cleanup=None, win_interrupt_evt=None):
        self.kernel = popen
        self.files_to_cleanup = files_to_cleanup or []
        self.win_interrupt_evt = win_interrupt_evt
        self.log = get_app_logger()
        self.kernel_id = str(uuid.uuid4())
        if not use_sync_subprocess:
            self._exit_future = asyncio.ensure_future(self.kernel.wait())

    async def wait(self):
        """Wait for kernel to terminate"""
        if use_sync_subprocess:
            sync_wait_timeout = 2
            try:
                self.kernel.wait(sync_wait_timeout)
            except subprocess.TimeoutExpired:
                self.log.warning("Timeout expired waiting for process '{}' to terminate.  Continuing...".
                                 format(self.kernel.pid))
        else:
            await self.kernel.wait()

    async def cleanup(self):
        """Clean up resources when the kernel is shut down"""
        # cleanup connection files on full shutdown of kernel we started
        for f in self.files_to_cleanup:
            try:
                os.remove(f)
            except (IOError, OSError, AttributeError):
                pass

    async def kill(self):
        """Kill the running kernel.
        """
        # Signal the kernel to terminate (sends SIGKILL on Unix and calls
        # TerminateProcess() on Win32).
        try:
            self.kernel.kill()
        except OSError as e:
            # In Windows, we will get an Access Denied error if the process
            # has already terminated. Ignore it.
            if sys.platform == 'win32':
                if e.winerror != 5:
                    raise
            # On Unix, we may get an ESRCH error if the process has already
            # terminated. Ignore it.
            else:
                from errno import ESRCH
                if e.errno != ESRCH:
                    raise

        # Wait until the kernel terminates.
        await self.wait()

    async def interrupt(self):
        """Interrupts the kernel by sending it a signal.

        Unlike ``signal_kernel``, this operation is well supported on all
        platforms.

        Kernels may ask for interrupts to be delivered by a message rather than
        a signal. This method does *not* handle that. Use KernelClient.interrupt
        to send a message or a signal as appropriate.
        """
        if sys.platform == 'win32':
            from .win_interrupt import send_interrupt
            send_interrupt(self.win_interrupt_evt)
        else:
            await self.signal(signal.SIGINT)

    async def signal(self, signum):
        """Sends a signal to the process group of the kernel (this
        usually includes the kernel and any subprocesses spawned by
        the kernel).

        Note that since only SIGTERM is supported on Windows, this function is
        only useful on Unix systems.
        """
        if hasattr(os, "getpgid") and hasattr(os, "killpg"):
            try:
                pgid = os.getpgid(self.kernel.pid)
                os.killpg(pgid, signum)
                return
            except OSError:
                pass
        self.kernel.send_signal(signum)

    async def is_alive(self):
        """Is the kernel process still running?"""
        if use_sync_subprocess:
            is_alive = False  # assume the kernel is dead
            if self.kernel is not None:
                if self.kernel.poll() is None:
                    is_alive = True

            return is_alive
        else:
            return not self._exit_future.done()
