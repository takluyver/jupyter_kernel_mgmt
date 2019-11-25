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

# Allow alteration via env since some kernels may require longer shutdown times.
max_wait_time = float(os.getenv("JKM_MAX_WAIT_TIME", 5.0))


class KernelManager(KernelManagerABC):
    """Manages a single kernel in a subprocess on this host.

    Parameters
    ----------

    popen : subprocess.Popen or asyncio.subprocess.Process
      The process with the started kernel.  Windows will use
      Popen (by default), while non-Windows will use asyncio's Process.
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
        # Capture subprocess kind from instance information
        self.async_subprocess = isinstance(popen, asyncio.subprocess.Process)
        if self.async_subprocess:
            self._exit_future = asyncio.ensure_future(self.kernel.wait())

    async def wait(self):
        """Wait for kernel to terminate"""
        if self.async_subprocess:
            await self.kernel.wait()
        else:
            # Use busy loop at 100ms intervals, polling until the process is
            # not alive.  If we find the process is no longer alive, complete
            # its cleanup via the blocking wait().  Callers are responsible for
            # issuing calls to wait() using a timeout (see kill()).
            while await self.is_alive():
                await asyncio.sleep(0.1)

            # Process is no longer alive, wait and clear
            if self.kernel is not None:
                self.kernel.wait()
                self.kernel = None

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
        try:
            await asyncio.wait_for(self.wait(), timeout=max_wait_time)
        except asyncio.TimeoutError:
            # Wait timed out, just log warning but continue - not much more we can do.
            self.log.warning("Wait for final termination of kernel '{id}' timed out - continuing...".
                             format(id=self.kernel_id))
            pass

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
        if self.async_subprocess:
            return not self._exit_future.done()
        else:
            return self.kernel and (self.kernel.poll() is None)
