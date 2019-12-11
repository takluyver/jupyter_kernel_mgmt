import asyncio
import argparse
import json
import logging
import os
import signal
from uuid import uuid4

from jupyter_core.paths import jupyter_runtime_dir, secure_write
from jupyter_core.utils import ensure_dir_exists

from . import __version__
from .discovery import KernelFinder
from .client import IOLoopKernelClient

log = logging.getLogger(__name__)


class KernelApp:
    """Launch a kernel by kernel type ID
    """
    def __init__(self, kernel_name='pyimport/kernel'):
        if '/' not in kernel_name:
            kernel_name = 'spec/' + kernel_name
        self.kernel_name = kernel_name
        self.shutdown_event = asyncio.Event()

    def setup_signals(self):
        """Shutdown on SIGTERM or SIGINT (Ctrl-C)"""
        if os.name == 'nt':
            return

        def shutdown_handler(signo):
            log.info('Shutting down on signal %d' % signo)
            self.shutdown_event.set()

        loop = asyncio.get_event_loop()
        for sig in [signal.SIGTERM, signal.SIGINT]:
            loop.add_signal_handler(sig, shutdown_handler, sig)

    async def shutdown(self, conn_info, manager):
        log.info("Shutting down kernel...")
        with IOLoopKernelClient(conn_info, manager=manager) as client:
            await client.shutdown_or_terminate()

    def record_connection_info(self, conn_info):
        log.info("Connection info: %s", conn_info)
        runtime_dir = jupyter_runtime_dir()
        ensure_dir_exists(runtime_dir)
        fname = os.path.join(runtime_dir, 'kernel-%s.json' % uuid4())

        # Only ever write this file as user read/writeable
        # This would otherwise introduce a vulnerability as a file has secrets
        # which would let others execute arbitrarily code as you
        with secure_write(fname) as f:
            f.write(json.dumps(conn_info, indent=2))

        log.info("To connect a client: --existing %s", os.path.basename(fname))
        return fname

    def _record_started(self):
        """For tests, create a file to indicate that we've started

        Do not rely on this except in our own tests!
        """
        fn = os.environ.get('JUPYTER_CLIENT_TEST_RECORD_STARTUP_PRIVATE')
        if fn is not None:
            with open(fn, 'wb'):
                pass

    async def run_in_loop(self):
        log.info('Starting kernel %r', self.kernel_name)
        kernel_finder = KernelFinder.from_entrypoints()
        conn_info, mgr = await kernel_finder.launch(self.kernel_name)
        try:
            self._record_started()
            conn_file = self.record_connection_info(conn_info)
            self.setup_signals()
            await asyncio.wait(
                [self.shutdown_event.wait(), mgr.wait()],
                return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            if await mgr.is_alive():
                await self.shutdown(conn_info, mgr)
            await mgr.cleanup()

        try:
            os.unlink(conn_file)
        except FileNotFoundError:
            pass

    def run(self):
        asyncio.get_event_loop().run_until_complete(self.run_in_loop())


def main(argv=None):
    ap = argparse.ArgumentParser(
        'jupyter-kernel', description="Run a kernel by kernel type ID"
    )
    ap.add_argument('--version', action='version', version=__version__)
    ap.add_argument('--kernel', default='pyimport/kernel',
        help="Kernel type to launch"
    )
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO)

    return KernelApp(args.kernel).run()

if __name__ == '__main__':
    main()
