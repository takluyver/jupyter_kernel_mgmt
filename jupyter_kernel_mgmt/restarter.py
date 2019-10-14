"""Machinery to monitor a KernelManager and restart the kernel if it dies
"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
from tornado import ioloop, gen
from traitlets.config.configurable import LoggingConfigurable
from traitlets import (
    Float,  Bool, Integer,
)

from .discovery import KernelFinder

class KernelRestarterBase(LoggingConfigurable):
    """Monitor and autorestart a kernel."""

    debug = Bool(False, config=True,
        help="""Whether to include every poll event in debugging output.

        Has to be set explicitly, because there will be *a lot* of output.
        """
    )

    time_to_dead = Float(3.0, config=True,
        help="""Kernel heartbeat interval in seconds."""
    )

    restart_limit = Integer(5, config=True,
        help="""The number of consecutive autorestarts before the kernel is presumed dead."""
    )

    _restarting = False
    _restart_count = 0

    def __init__(self, kernel_manager, kernel_type, kernel_finder=None, **kw):
        super(KernelRestarterBase, self).__init__(**kw)
        self.kernel_manager = kernel_manager
        self.kernel_type = kernel_type
        self.kernel_finder = kernel_finder or KernelFinder.from_entrypoints()
        self.callbacks = dict(died=[], restarted=[], failed=[])

    def start(self):
        """Start monitoring the kernel."""
        raise NotImplementedError("Must be implemented in a subclass")

    def stop(self):
        """Stop monitoring."""
        raise NotImplementedError("Must be implemented in a subclass")

    def add_callback(self, f, event):
        """
        Register a callback to fire on a particular event.

        Possible values for event:
          'died': the monitored kernel has died

          'restarted': a restart has been attempted (this does not necessarily mean that the new kernel is usable).

          'failed': *restart_limit* attempts have failed in quick succession, and the restarter is giving up.
        """
        self.callbacks[event].append(f)

    def remove_callback(self, f, event):
        """Unregister a callback from a particular event

        Possible values for *event* are the same as in :meth:`add_callback`.
        """
        try:
            self.callbacks[event].remove(f)
        except ValueError:
            pass

    def _fire_callbacks(self, event, data):
        """fire our callbacks for a particular event"""
        for callback in self.callbacks[event]:
            try:
                callback(data)
            except Exception as e:
                self.log.error("KernelRestarter: %s callback %r failed", event, callback, exc_info=True)

    async def do_restart(self, auto=False):
        """Called when the kernel has died"""
        if auto and self._restarting:
            self._restart_count += 1
        else:
            self._restart_count = 1

        if self._restart_count >= self.restart_limit:
            self.log.warning("KernelRestarter: restart failed")
            self._fire_callbacks('failed', {
                'restart_count': self._restart_count,
            })
            self._restarting = False
            self._restart_count = 0
            self.stop()
        else:
            cwd = getattr(self.kernel_manager, 'cwd', None)  # :-/
            self.log.info("KernelRestarter: starting new manager (%i/%i)",
                          self._restart_count, self.restart_limit)
            await self.kernel_manager.cleanup()
            conn_info, mgr = await self.kernel_finder.launch(self.kernel_type, cwd)
            self._fire_callbacks('restarted', {
                'auto': auto,
                'connection_info': conn_info,
                'manager': mgr,
            })
            self.kernel_manager = mgr
            self._restarting = True

    async def poll(self):
        if self.debug:
            self.log.debug('Polling kernel...')
        if not await self.kernel_manager.is_alive():
            self._fire_callbacks('died', {})
            await self.do_restart(auto=True)
        else:
            if self._restarting:
                self.log.debug("KernelRestarter: restart apparently succeeded")
            self._restarting = False


class TornadoKernelRestarter(KernelRestarterBase):
    """Monitor a kernel using the tornado ioloop."""
    _pcallback = None

    def start(self):
        """Start the polling of the kernel."""
        if self._pcallback is None:
            self._pcallback = ioloop.PeriodicCallback(
                self.poll, 1000*self.time_to_dead,
            )
            self._pcallback.start()

    def stop(self):
        """Stop the kernel polling."""
        if self._pcallback is not None:
            self._pcallback.stop()
            self._pcallback = None

    def _fire_callbacks(self, event, data):
        loop = ioloop.IOLoop.current()
        for callback in self.callbacks[event]:
            loop.add_callback(callback, data)
