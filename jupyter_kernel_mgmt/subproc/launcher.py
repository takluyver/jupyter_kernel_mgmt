"""Machinery for launching a kernel in a local subprocess.
"""
import asyncio
from binascii import b2a_hex
from contextlib import contextmanager
import errno
import json
import os
import re
import socket
import stat
from subprocess import PIPE, Popen
import sys
from traitlets.log import get_logger as get_app_logger
import warnings

from jupyter_core.paths import jupyter_runtime_dir, secure_write
from jupyter_core.utils import ensure_dir_exists
from ..localinterfaces import localhost, is_local_ip, local_ips
from .manager import KernelManager
from ..util import run_sync

port_names = ['shell_port', 'iopub_port', 'stdin_port', 'control_port', 'hb_port']

# Abstract the decision on whether to use a sync popen so we
# can easily enable it on non-windows systems if necessary.
# This value should remain True for win32 until
# asyncio.create_subprocess_exec works (see comment in
# util.init_asyncio_patch()).
if sys.platform == 'win32':
    use_sync_subprocess = True
else:
    use_sync_subprocess = False


class SubprocessKernelLauncher:
    """Run a kernel asynchronously in a subprocess.

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
    transport = 'tcp'

    def __init__(self, kernel_cmd, cwd, extra_env=None, ip=None, launch_params=None):
        self.kernel_cmd = kernel_cmd
        self.cwd = cwd
        self.extra_env = extra_env
        if ip is None:
            ip = localhost()
        self.ip = ip
        self.launch_params = launch_params
        self.log = get_app_logger()

        if self.transport == 'tcp' and not is_local_ip(ip):
            raise RuntimeError("Can only launch a kernel on a local interface. "
                               "Make sure that the '*_address' attributes are "
                               "configured properly. "
                               "Currently valid addresses are: %s" % local_ips()
                               )

    async def launch(self):
        """The main method to launch a kernel.

        Returns (connection_info,  kernel_manager)
        """
        conn_file, conn_info = self.make_connection_file()

        kw = self.build_popen_kwargs(conn_file)
        win_interrupt_evt = prepare_interrupt_event(kw['env'])

        # launch the kernel subprocess
        args = kw.pop('args')
        self.log.debug("Starting kernel cmd: %s", args)

        if use_sync_subprocess:
            kernel = Popen(args, **kw)
        else:
            kernel = await asyncio.create_subprocess_exec(*args, **kw)
        kernel.stdin.close()

        files_to_cleanup = list(self.files_to_cleanup(conn_file, conn_info))
        mgr = KernelManager(kernel, files_to_cleanup, win_interrupt_evt=win_interrupt_evt)
        return conn_info, mgr

    def files_to_cleanup(self, connection_file, connection_info):
        """Find files to be cleaned up after this kernel is finished.

        This method is mostly to be overridden for cleaning up IPC sockets.
        """
        yield connection_file

    def make_ports(self):
        """Randomly select available ports for each of port_names"""
        res = {}
        # store sockets temporarily to avoid reusing a port number
        tmp_socks = []
        for _ in port_names:
            sock = socket.socket()
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b'\0' * 8)
            sock.bind((self.ip, 0))
            tmp_socks.append(sock)
        for name, sock in zip(port_names, tmp_socks):
            port = sock.getsockname()[1]
            sock.close()
            res[name] = port

        return res

    def make_connection_file(self):
        """Generates a JSON config file, including the selection of random ports.
        """
        runtime_dir = jupyter_runtime_dir()
        ensure_dir_exists(runtime_dir)
        fname = os.path.join(runtime_dir, 'kernel-%s.json' % new_key())

        cfg = self.make_ports()
        cfg['ip'] = self.ip
        cfg['key'] = new_key()
        cfg['transport'] = self.transport
        cfg['signature_scheme'] = 'hmac-sha256'

        # Only ever write this file as user read/writeable
        # This would otherwise introduce a vulnerability as a file has secrets
        # which would let others execute arbitrarily code as you
        with secure_write(fname) as f:
            f.write(json.dumps(cfg, indent=2))

        set_sticky_bit(fname)

        return fname, cfg

    def format_kernel_cmd(self, connection_file, kernel_resource_dir=None):
        """Replace templated args (e.g. {connection_file})
        """
        cmd = self.kernel_cmd.copy()

        if cmd and cmd[0] == 'python':
            # executable is 'python', use sys.executable.
            # These will typically be the same,
            # but if the current process is in an env
            # and has been launched by abspath without
            # activating the env, python on PATH may not be sys.executable,
            # but it should be.
            cmd[0] = sys.executable

        # Preserve system-owned substitutions by starting with launch params
        ns = dict()
        if isinstance(self.launch_params, dict):
            ns.update(self.launch_params)

        # Add system-owned substitutions
        ns.update(dict(connection_file=connection_file,
                  prefix=sys.prefix,
                  ))

        if kernel_resource_dir:
            ns["resource_dir"] = kernel_resource_dir

        pat = re.compile(r'{([A-Za-z0-9_]+)}')

        def from_ns(match):
            """Get the key out of ns if it's there, otherwise no change.
               Return as string since that's what is required by pattern
               matching.  We know this should be safe currently, because
               only 'connection_file', 'sys.prefix' and 'resource_dir' are
               candidates - all of which are strings.
            """
            return str(ns.get(match.group(1), match.group()))

        return [pat.sub(from_ns, arg) for arg in cmd]

    def build_popen_kwargs(self, connection_file):
        """Build a dictionary of arguments to pass to Popen"""
        kwargs = {}
        # Popen will fail (sometimes with a deadlock) if stdin, stdout, and stderr
        # are invalid. Unfortunately, there is in general no way to detect whether
        # they are valid.  The following two blocks redirect them to (temporary)
        # pipes in certain important cases.

        # If this process has been backgrounded, our stdin is invalid. Since there
        # is no compelling reason for the kernel to inherit our stdin anyway, we'll
        # place this one safe and always redirect.
        kwargs['stdin'] = PIPE

        # If this process in running on pythonw, we know that stdin, stdout, and
        # stderr are all invalid.
        redirect_out = sys.executable.endswith('pythonw.exe')
        if redirect_out:
            kwargs['stdout'] = kwargs['stderr'] = open(os.devnull, 'w')

        cmd = self.format_kernel_cmd(connection_file)

        kwargs['env'] = env = os.environ.copy()
        # Don't allow PYTHONEXECUTABLE to be passed to kernel process.
        # If set, it can bork all the things.
        env.pop('PYTHONEXECUTABLE', None)

        if self.extra_env:
            env.update(self.extra_env)

        # TODO: where is this used?
        independent = False

        if sys.platform == 'win32':
            kwargs['args'] = cmd
            if self.cwd:
                kwargs['cwd'] = self.cwd

            try:
                # noinspection PyUnresolvedReferences
                from _winapi import DuplicateHandle, GetCurrentProcess, \
                    DUPLICATE_SAME_ACCESS, CREATE_NEW_PROCESS_GROUP
            except:
                # noinspection PyUnresolvedReferences
                from _subprocess import DuplicateHandle, GetCurrentProcess, \
                    DUPLICATE_SAME_ACCESS, CREATE_NEW_PROCESS_GROUP
            # Launch the kernel process
            if independent:
                kwargs['creationflags'] = CREATE_NEW_PROCESS_GROUP
            else:
                pid = GetCurrentProcess()
                handle = DuplicateHandle(pid, pid, pid, 0,
                                         True,  # Inheritable by new processes.
                                         DUPLICATE_SAME_ACCESS)
                env['JPY_PARENT_PID'] = str(int(handle))

            # Prevent creating new console window on pythonw
            if redirect_out:
                kwargs['creationflags'] = kwargs.setdefault('creationflags', 0) | 0x08000000 # CREATE_NO_WINDOW

            # Avoid closing the above parent and interrupt handles.
            # close_fds is True by default on Python >=3.7
            # or when no stream is captured on Python <3.7
            # (we always capture stdin, so this is already False by default on <3.7)
            kwargs['close_fds'] = False

        else:
            kwargs['args'] = cmd
            kwargs['cwd'] = self.cwd
            # Create a new session.
            # This makes it easier to interrupt the kernel,
            # because we want to interrupt the whole process group.
            # We don't use setpgrp, which is known to cause problems for kernels starting
            # certain interactive subprocesses, such as bash -i.
            kwargs['start_new_session'] = True
            if not independent:
                env['JPY_PARENT_PID'] = str(os.getpid())

        return kwargs


class SubprocessIPCKernelLauncher(SubprocessKernelLauncher):
    """Start a kernel on this machine to listen on IPC (filesystem) sockets"""
    transport = 'ipc'

    def make_ports(self):
        res = {}
        N = 1
        for name in port_names:
            while os.path.exists("%s-%s" % (self.ip, str(N))):
                N += 1
            res[name] = N
            N += 1

        return res

    def files_to_cleanup(self, connection_file, connection_info):
        yield from super().files_to_cleanup(connection_file, connection_info)
        ports = [v for (k, v) in connection_info.items()
                 if k.endswith('_port')]
        for port in ports:
            yield "%s-%i" % (connection_info['ip'], port)


def new_key():
    """Generate a new random key string.

    Avoids problematic runtime import in stdlib uuid on Python 2.

    Returns
    -------

    id string (16 random bytes as hex-encoded text, chunks separated by '-')
    """
    buf = os.urandom(16)
    return u'-'.join(b2a_hex(x).decode('ascii') for x in (
        buf[:4], buf[4:]
    ))


def set_sticky_bit(fname):
    """Set the sticky bit on the file and its parent directory.

    This stops it being deleted by periodic cleanup of XDG_RUNTIME_DIR.
    """
    if not hasattr(stat, 'S_ISVTX'):
        return

    paths = [fname]
    runtime_dir = os.path.dirname(fname)
    if runtime_dir:
        paths.append(runtime_dir)
    for path in paths:
        permissions = os.stat(path).st_mode
        new_permissions = permissions | stat.S_ISVTX
        if new_permissions != permissions:
            try:
                os.chmod(path, new_permissions)
            except OSError as e:
                if e.errno == errno.EPERM and path == runtime_dir:
                    # suppress permission errors setting sticky bit on runtime_dir,
                    # which we may not own.
                    pass
                else:
                    # failed to set sticky bit, probably not a big deal
                    warnings.warn(
                        "Failed to set sticky bit on %r: %s"
                        "\nProbably not a big deal, but runtime files may be cleaned up periodically." % (path, e),
                        RuntimeWarning,
                    )


def prepare_interrupt_event(env, interrupt_event=None):
    if sys.platform == 'win32':
        from .win_interrupt import create_interrupt_event
        # Create a Win32 event for interrupting the kernel
        # and store it in an environment variable.
        if interrupt_event is None:
            interrupt_event = create_interrupt_event()
        env["JPY_INTERRUPT_EVENT"] = str(interrupt_event)
        # deprecated old env name:
        env["IPY_INTERRUPT_EVENT"] = env["JPY_INTERRUPT_EVENT"]
        return interrupt_event

