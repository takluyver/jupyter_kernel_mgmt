"""Base class to manage the interaction with a running kernel"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from __future__ import absolute_import, print_function

import time

from traitlets.log import get_logger as get_app_logger
from jupyter_protocol.messages import (
    Message, execute_request, complete_request, inspect_request,
    history_request, kernel_info_request, comm_info_request, shutdown_request,
    is_complete_request, interrupt_request, input_reply,
)
from jupyter_protocol.sockets import ClientMessaging
from jupyter_protocol._version import protocol_version_info
from .managerabc import KernelManagerABC

monotonic = time.monotonic

major_protocol_version = protocol_version_info[0]


class ManagerClient(KernelManagerABC):
    def __init__(self, messaging, connection_info):
        self.messaging = messaging
        self.connection_info = connection_info

    def is_alive(self):
        """Check whether the kernel is currently alive (e.g. the process exists)
        """
        msg = Message.from_type('is_alive_request', {})
        self.messaging.send('nanny_control', msg)

        while True:
            self.messaging.nanny_control_socket.poll()
            reply = self.messaging.recv('nanny_control')
            if reply.parent_header['msg_id'] == msg.header['msg_id']:
                return reply.content['alive']

    def wait(self, timeout):
        """Wait for the kernel process to exit.

        If timeout is a number, it is a maximum time in seconds to wait.
        timeout=None means wait indefinitely.

        Returns True if the kernel is still alive after waiting, False if it
        exited (like is_alive()).
        """
        if timeout is not None:
            deadline = monotonic() + timeout
        else:
            deadline = 0
        # First check if the kernel is alive, in case it died before we got
        # any messages.
        if not self.is_alive():
            return False

        if timeout is None:
            while True:
                self.messaging.nanny_events_socket.poll()
                reply = self.messaging.recv('nanny_events')
                if reply.header['msg_type'] == 'kernel_died':
                    return False

        timeout = deadline - monotonic()
        events_socket = self.messaging.nanny_events_socket
        while timeout > 0:
            ready = events_socket.poll(timeout=timeout*1000)
            if ready:
                msg = self.messaging.recv('nanny_events')
                if msg.header['msg_type'] == 'kernel_died':
                    return False
            timeout = deadline - monotonic()

        return True

    def signal(self, signum):
        """Send a signal to the kernel."""
        raise NotImplementedError

    def interrupt(self):
        """Interrupt the kernel by sending it a signal or similar event

        Kernels can request to get interrupts as messages rather than signals.
        The manager is *not* expected to handle this.
        :meth:`.KernelClient2.interrupt` should send an interrupt_request or
        call this method as appropriate.
        """
        msg = Message.from_type('interrupt_request', {})
        self.messaging.send('nanny_control', msg)

    def kill(self):
        """Forcibly terminate the kernel.

        This method may be used to dispose of a kernel that won't shut down.
        Working kernels should usually be shut down by sending shutdown_request
        from a client and giving it some time to clean up.
        """
        msg = Message.from_type('kill_request', {})
        self.messaging.send('nanny_control', msg)

    def get_connection_info(self):
        """Return a dictionary of connection information"""
        return self.connection_info

    def relaunch(self):
        """Attempt to relaunch the kernel using the same ports.

        This is meant to be called after the managed kernel has died. Calling
        it while the kernel is still alive has undefined behaviour.

        Returns True if this manager supports that.
        """
        return False


class KernelClient(object):
    """Communicates with a single kernel on any host via zmq channels.

    The messages that can be sent are exposed as methods of the
    client (KernelClient2.execute, complete, history, etc.). These methods only
    send the message, they don't wait for a reply. To get results, use e.g.
    :meth:`get_shell_msg` to fetch messages from the shell channel.
    """
    hb_monitor = None

    def __init__(self, connection_info, manager=None, use_heartbeat=True):
        self.connection_info = connection_info
        self.messaging = ClientMessaging(connection_info)
        if (manager is None) and 'nanny_control_port' in connection_info:
            self.manager = ManagerClient(self.messaging, connection_info)
        else:
            self.manager = manager

        self.session = self.messaging.session
        self.log = get_app_logger()

        # if self.using_heartbeat:
        #     self.hb_monitor = HBChannel(context=self.context,
        #                                 address=self._make_url('hb'))
        #     self.hb_monitor.start()

    @property
    def owned_kernel(self):
        """True if this client 'owns' the kernel, i.e. started it."""
        return self.manager is not None

    def close(self):
        """Close sockets of this client.

        After calling this, the client can no longer be used.
        """
        self.messaging.close()
        if self.hb_monitor:
            self.hb_monitor.stop()

    # flag for whether execute requests should be allowed to call raw_input:
    allow_stdin = True

    def is_alive(self):
        if self.owned_kernel:
            return self.manager.is_alive()
        elif self.using_heartbeat:
            return self.hb_monitor.is_beating()
        else:
            return True  # Fingers crossed

    def _send(self, socket, msg):
        self.session.send(socket, msg)

    # Methods to send specific messages on channels
    def execute(self, code, silent=False, store_history=True,
                user_expressions=None, allow_stdin=None, stop_on_error=True,
                _header=None):
        """Execute code in the kernel.

        Parameters
        ----------
        code : str
            A string of code in the kernel's language.

        silent : bool, optional (default False)
            If set, the kernel will execute the code as quietly possible, and
            will force store_history to be False.

        store_history : bool, optional (default True)
            If set, the kernel will store command history.  This is forced
            to be False if silent is True.

        user_expressions : dict, optional
            A dict mapping names to expressions to be evaluated in the user's
            dict. The expression values are returned as strings formatted using
            :func:`repr`.

        allow_stdin : bool, optional (default self.allow_stdin)
            Flag for whether the kernel can send stdin requests to frontends.

            Some frontends (e.g. the Notebook) do not support stdin requests.
            If raw_input is called from code executed from such a frontend, a
            StdinNotImplementedError will be raised.

        stop_on_error: bool, optional (default True)
            Flag whether to abort the execution queue, if an exception is encountered.

        Returns
        -------
        The msg_id of the message sent.
        """
        msg = execute_request(code, silent=silent, store_history=store_history,
              user_expressions=user_expressions, allow_stdin=allow_stdin,
              stop_on_error=stop_on_error)
        if _header:
            msg.header = _header
        self.messaging.send('shell', msg)
        return msg.header['msg_id']

    def complete(self, code, cursor_pos=None, _header=None):
        """Tab complete text in the kernel's namespace.

        Parameters
        ----------
        code : str
            The context in which completion is requested.
            Can be anything between a variable name and an entire cell.
        cursor_pos : int, optional
            The position of the cursor in the block of code where the completion was requested.
            Default: ``len(code)``

        Returns
        -------
        The msg_id of the message sent.
        """
        msg = complete_request(code, cursor_pos=cursor_pos)
        if _header:
            msg.header = _header
        self.messaging.send('shell', msg)
        return msg.header['msg_id']

    def inspect(self, code, cursor_pos=None, detail_level=0, _header=None):
        """Get metadata information about an object in the kernel's namespace.

        It is up to the kernel to determine the appropriate object to inspect.

        Parameters
        ----------
        code : str
            The context in which info is requested.
            Can be anything between a variable name and an entire cell.
        cursor_pos : int, optional
            The position of the cursor in the block of code where the info was requested.
            Default: ``len(code)``
        detail_level : int, optional
            The level of detail for the introspection (0-2)

        Returns
        -------
        The msg_id of the message sent.
        """
        msg = inspect_request(code, cursor_pos=cursor_pos, detail_level=detail_level)
        if _header:
            msg.header = _header
        self.messaging.send('shell', msg)
        return msg.header['msg_id']

    def history(self, raw=True, output=False, hist_access_type='range',
                _header=None, **kwargs):
        """Get entries from the kernel's history list.

        Parameters
        ----------
        raw : bool
            If True, return the raw input.
        output : bool
            If True, then return the output as well.
        hist_access_type : str
            'range' (fill in session, start and stop params), 'tail' (fill in n)
             or 'search' (fill in pattern param).

        session : int
            For a range request, the session from which to get lines. Session
            numbers are positive integers; negative ones count back from the
            current session.
        start : int
            The first line number of a history range.
        stop : int
            The final (excluded) line number of a history range.

        n : int
            The number of lines of history to get for a tail request.

        pattern : str
            The glob-syntax pattern for a search request.

        Returns
        -------
        The ID of the message sent.
        """
        msg = history_request(raw=raw, output=output,
                              hist_access_type=hist_access_type, **kwargs)
        if _header:
            msg.header = _header
        self.messaging.send('shell', msg)
        return msg.header['msg_id']

    def kernel_info(self, _header=None):
        """Request kernel info

        Returns
        -------
        The msg_id of the message sent
        """
        msg = kernel_info_request()
        if _header:
            msg.header = _header
        self.messaging.send('shell', msg)
        return msg.header['msg_id']

    def comm_info(self, target_name=None, _header=None):
        """Request comm info

        Returns
        -------
        The msg_id of the message sent
        """
        msg = comm_info_request(target_name)
        if _header:
            msg.header = _header
        self.messaging.send('shell', msg)
        return msg.header['msg_id']

    def _handle_kernel_info_reply(self, msg):
        """handle kernel info reply

        sets protocol adaptation version. This might
        be run from a separate thread.
        """
        adapt_version = int(msg.content['protocol_version'].split('.')[0])
        if adapt_version != major_protocol_version:
            self.session.adapt_version = adapt_version

    def shutdown(self, restart=False, _header=None):
        """Request an immediate kernel shutdown.

        Upon receipt of the (empty) reply, client code can safely assume that
        the kernel has shut down and it's safe to forcefully terminate it if
        it's still alive.

        The kernel will send the reply via a function registered with Python's
        atexit module, ensuring it's truly done as the kernel is done with all
        normal operation.

        Returns
        -------
        The msg_id of the message sent
        """
        # Send quit message to kernel. Once we implement kernel-side setattr,
        # this should probably be done that way, but for now this will do.
        msg = shutdown_request(restart)
        if _header:
            msg.header = _header
        self.messaging.send('shell', msg)
        return msg.header['msg_id']

    def is_complete(self, code, _header=None):
        """Ask the kernel whether some code is complete and ready to execute."""
        msg = is_complete_request(code)
        if _header:
            msg.header = _header
        self.messaging.send('shell', msg)
        return msg.header['msg_id']

    def interrupt(self, _header=None):
        """Send an interrupt message/signal to the kernel"""
        mode = self.connection_info.get('interrupt_mode', 'signal')
        if mode == 'message':
            msg = interrupt_request()
            if _header:
                msg.header = _header
            self.messaging.send('shell', msg)
            return msg['header']['msg_id']
        elif self.owned_kernel:
            self.manager.interrupt()
        else:
            self.log.warning("Can't send signal to non-owned kernel")

    def input(self, string, parent=None):
        """Send a string of raw input to the kernel.

        This should only be called in response to the kernel sending an
        ``input_request`` message on the stdin channel.
        """
        msg = input_reply(string, parent=parent)
        self.messaging.send('stdin', msg)

    @property
    def shell_socket(self):  # For convenience
        return self.messaging.sockets['shell']

    @property
    def iopub_socket(self):
        return self.messaging.sockets['iopub']

    @property
    def stdin_socket(self):
        return self.messaging.sockets['stdin']

