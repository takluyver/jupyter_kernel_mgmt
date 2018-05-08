import asyncio
import os

from .launcher import SubprocessKernelLauncher, prepare_interrupt_event
from .manager import KernelManager
from ..util import inherit_docstring

class AsyncSubprocessKernelLauncher(SubprocessKernelLauncher):
    """Run a kernel asynchronously in a subprocess.

    This is the async counterpart to SubprocessKernelLauncher.

    Parameters
    ----------

    kernel_cmd : list of str
      The Popen command template to launch the kernel
    cwd : str
      The working directory to launch the kernel in
    extra_env : dict, optional
      Dictionary of environment variables to update the existing environment
    ip : str, optional
      Set the kernel\'s IP address [default localhost].
      If the IP address is something other than localhost, then
      Consoles on other machines will be able to connect
      to the Kernel, so be careful!
    """

    @asyncio.coroutine
    def launch(self):
        """The main method to launch a kernel.

        Returns (connection_info,  kernel_manager)
        """
        conn_file, conn_info = self.make_connection_file()

        kw = self.build_popen_kwargs(conn_file)
        win_interrupt_evt = prepare_interrupt_event(kw['env'])

        # launch the kernel subprocess
        args = kw.pop('args')
        self.log.debug("Starting kernel cmd: %s", args)
        kernel = yield from asyncio.create_subprocess_exec(*args, **kw)
        kernel.stdin.close()

        files_to_cleanup = list(self.files_to_cleanup(conn_file, conn_info))
        mgr = AsyncPopenKernelManager(kernel, files_to_cleanup,
                                      win_interrupt_evt=win_interrupt_evt)
        return conn_info, mgr

class AsyncPopenKernelManager(KernelManager):
    @inherit_docstring(KernelManager)
    def __init__(self, proc, files_to_cleanup=None, win_interrupt_evt=None):
        super().__init__(proc, files_to_cleanup, win_interrupt_evt)
        self._exit_future = asyncio.ensure_future(self.kernel.wait())

    @inherit_docstring(KernelManager)
    @asyncio.coroutine
    def wait(self, timeout):
        try:
            yield from asyncio.wait_for(self.kernel.wait(), timeout)
            return False
        except asyncio.TimeoutError:
            return True

    @inherit_docstring(KernelManager)
    @asyncio.coroutine
    def is_alive(self):
        return not self._exit_future.done()

    @inherit_docstring(KernelManager)
    @asyncio.coroutine
    def signal(self, signum):
        return super().signal(signum)

    @inherit_docstring(KernelManager)
    @asyncio.coroutine
    def interrupt(self):
        return super().interrupt()

    @inherit_docstring(KernelManager)
    @asyncio.coroutine
    def kill(self):
        return super().kill()

    @inherit_docstring(KernelManager)
    @asyncio.coroutine
    def cleanup(self):
        return super().cleanup()

@asyncio.coroutine
def start_new_kernel(kernel_cmd, startup_timeout=60, cwd=None):
    """Start a new kernel, and return its Manager and a blocking client"""
    from ..client import IOLoopKernelClient
    cwd = cwd or os.getcwd()

    launcher = AsyncSubprocessKernelLauncher(kernel_cmd, cwd=cwd)
    info, km = yield from launcher.launch()
    kc = IOLoopKernelClient(info, manager=km)
    try:
        yield from asyncio.wait_for(kc.wait_for_ready(), timeout=startup_timeout)
    except RuntimeError:
        yield from kc.shutdown_or_terminate()
        raise

    return km, kc
