"""Clients built around a tornado IOLoop.
"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import atexit
from datetime import timedelta
import errno
from functools import partial, wraps
from getpass import getpass
import sys
from threading import Thread, Event
import time
from tornado.concurrent import Future
from tornado import gen
from tornado import ioloop
import tornado.util
from zmq import ZMQError
from zmq.eventloop import zmqstream

from jupyter_protocol.messages import (
    execute_request, complete_request, inspect_request, history_request,
    kernel_info_request, comm_info_request, shutdown_request, is_complete_request,
    interrupt_request, input_reply,
)
from .client_base import KernelClient
from .util import inherit_docstring

DEBUG_LOGGING = False


class ErrorInKernel(Exception):
    def __init__(self, reply_msg):
        self.reply_msg = reply_msg

    def __str__(self):
        c = self.reply_msg.content
        return '\n'.join(c.get('traceback', [])
                         + ['{}: {}'.format(c.get('ename', 'ERROR'), c.get('evalue', ''))])

class IOLoopKernelClient(KernelClient):
    """Uses a zmq/tornado IOLoop to handle received messages and fire callbacks.

    Use ClientInThread to run this in a separate thread alongside your
    application.
    """
    def __init__(self, connection_info, manager=None):
        super(IOLoopKernelClient, self).__init__(connection_info, manager)
        self.ioloop = ioloop.IOLoop.current()
        self.request_futures = {}
        self._iopub_ready = False
        self.handlers = {
            'iopub': [self._set_iopub_ready],
            'shell': [self._auto_adapt, self._fulfil_request],
            'stdin': [],
            'control': [self._fulfil_request],
        }
        self.streams = {}
        for channel, socket in self.messaging.sockets.items():
            self.streams[channel] = s = zmqstream.ZMQStream(socket, self.ioloop)
            s.on_recv(partial(self._handle_recv, channel))

        if DEBUG_LOGGING:
            for channel in ('iopub', 'shell', 'stdin', 'control'):
                self.add_handler(channel, partial(self._debug_log, channel))

    def close(self):
        """Close the client's sockets & streams.

        This does not close the IOLoop.
        """
        for stream in self.streams.values():
            stream.close()
        if self.hb_monitor:
            self.hb_monitor.stop()

    def _debug_log(self, channel, msg):
        print(channel, msg.header['msg_id'][:8], msg.header['msg_type'], 'parent:', msg.parent_header.get('msg_id', '-')[:8])

    def _auto_adapt(self, msg):
        """Use the first kernel_info_reply to set up protocol version adaptation
        """
        if msg.header['msg_type'] == 'kernel_info_reply':
            self._handle_kernel_info_reply(msg)
            self.remove_handler('shell', self._auto_adapt)

    def _request_future(self, msg_id):
        self.request_futures[msg_id] = f = Future()
        return f

    def _fulfil_request(self, msg):
        """If msg is a reply, set the result for the request future."""
        if msg.header['msg_type'].endswith('_reply'):
            parent_id = msg.parent_header.get('msg_id')
            parent_future = self.request_futures.pop(parent_id, None)
            if parent_future and not parent_future.cancelled():
                if msg.content.get('status', 'ok') == 'error':
                    e = ErrorInKernel(msg)
                    parent_future.set_exception(e)
                else:
                    parent_future.set_result(msg)

    def _handle_recv(self, channel, wire_msg):
        """Callback for stream.on_recv.

        Unpacks message, and calls handlers with it.
        """
        msg = self.session.deserialize(wire_msg)
        self._call_handlers(channel, msg)

    def _call_handlers(self, channel, msg):
        # [:] copies the list - handlers that remove themselves (or add other
        # handlers) will not mess up iterating over it.
        for handler in self.handlers[channel][:]:
            try:
                handler(msg)
            except Exception as e:
                self.log.error("Exception from message handler %r", handler,
                               exc_info=e)

    def add_handler(self, channel, handler):
        """Add a callback for received messages on one channel.

        Parameters
        ----------

        channel : str
          One of 'shell', 'iopub', 'stdin' or 'control'
        handler : function
          Will be called for each message received with the message dictionary
          as a single argument.
        """
        self.handlers[channel].append(handler)

    def remove_handler(self, channel, handler):
        """Remove a previously registered callback."""
        self.handlers[channel].remove(handler)

    # Methods to send specific messages.
    # These requests all return a Future, which completes when the reply arrives
    @gen.coroutine
    def execute(self, code, silent=False, store_history=True,
                user_expressions=None, allow_stdin=None, stop_on_error=True,
                interrupt_timeout=None, idle_timeout=None, raise_on_no_idle=False, _header=None):
        msg_id = super().execute(code, silent=silent, store_history=store_history,
              user_expressions=user_expressions, allow_stdin=allow_stdin,
              stop_on_error=stop_on_error, _header=_header)
        # print("Sent execute_request", msg_id[:8])
        request_fut = self._request_future(msg_id)
        if not (interrupt_timeout or idle_timeout):
            return (yield from request_fut)

        interrupt_cb = None
        if interrupt_timeout:
            interrupt_cb = self.ioloop.call_later(interrupt_timeout,
                                                  self.interrupt)

        got_idle_fut = Future()
        def watch_for_idle(msg):
            if msg.header['msg_type'] == 'status' \
                    and msg.parent_header.get('msg_id') == msg_id \
                    and msg.content['execution_state'] == 'idle':
                got_idle_fut.set_result(msg)
        self.add_handler('iopub', watch_for_idle)

        try:
            try:
                reply = yield from request_fut
            except ErrorInKernel as e:
                reply = e.reply_msg
            if interrupt_cb is not None:
                self.ioloop.remove_timeout(interrupt_cb)

            if idle_timeout:
                # Wait for idle message -
                # this may resolve immediately if we already got it.
                try:
                    yield from gen.with_timeout(timedelta(seconds=idle_timeout),
                                                got_idle_fut)
                except ioloop.TimeoutError:
                    print("Timed out waiting for idle")
                    if raise_on_no_idle:
                        raise
        finally:
            self.remove_handler('iopub', watch_for_idle)

        if reply.content.get('status', 'ok') == 'error':
            raise ErrorInKernel(reply)
        return reply

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
        msg_id = super().complete(code, cursor_pos=cursor_pos, _header=_header)
        return self._request_future(msg_id)

    def inspect(self, code, cursor_pos=None, detail_level=0, _header=None):
        msg_id = super().inspect(code, cursor_pos=cursor_pos,
                                 detail_level=detail_level, _header=_header)
        return self._request_future(msg_id)

    def history(self, raw=True, output=False, hist_access_type='range',
                _header=None, **kwargs):
        msg_id = super().history(raw=raw, output=output,
                   hist_access_type=hist_access_type, _header=_header, **kwargs)
        return self._request_future(msg_id)

    def kernel_info(self, _header=None):
        msg_id = super().kernel_info(_header=_header)
        # print("Send kernel_info_request", msg_id[:8])
        return self._request_future(msg_id)

    def comm_info(self, target_name=None, _header=None):
        msg_id = super().comm_info(target_name, _header=_header)
        return self._request_future(msg_id)

    def shutdown(self, restart=False, _header=None):
        msg_id = super().shutdown(restart, _header=_header)
        return self._request_future(msg_id)

    @gen.coroutine
    def shutdown_or_terminate(self, timeout=5.0):
        """Ask the kernel to shut down, and terminate it if it takes too long.

        The kernel will be given up to timeout seconds to shut itself down.
        """
        if not self.manager:
            raise RuntimeError(
                "Cannot terminate a kernel without a KernelManager")
        try:
            yield gen.with_timeout(timedelta(seconds=timeout), self.shutdown())
        except tornado.util.TimeoutError:
            self.log.debug("Kernel is taking too long to finish, killing")
            self.manager.kill()
        self.manager.cleanup()

    @gen.coroutine
    def wait_for_ready(self):
        second = timedelta(seconds=1)

        # Repeatedly do kernel info requests until our iopub subscription works.
        while True:
            reply_fut = self.kernel_info()
            while True:
                try:
                    yield from gen.with_timeout(second, reply_fut)
                except tornado.util.TimeoutError:
                    pass
                else:
                    break

                if not self.is_alive():
                    raise RuntimeError(
                        'Kernel died before replying to kernel_info')

            if self._iopub_ready:
                return
            yield from gen.sleep(0.01)

    def _set_iopub_ready(self, msg):
        self._iopub_ready = True
        self.remove_handler('iopub', self._set_iopub_ready)

    def is_complete(self, code, _header=None):
        """Ask the kernel whether some code is complete and ready to execute."""
        msg_id = super().is_complete(code, _header=_header)
        return self._request_future(msg_id)

    def interrupt(self, _header=None):
        """Send an interrupt message/signal to the kernel"""
        mode = self.connection_info.get('interrupt_mode', 'signal')
        if mode == 'message':
            msg_id = super().interrupt(_header=_header)
            return self._request_future(msg_id)
        elif self.owned_kernel:
            self.manager.interrupt()
        else:
            self.log.warning("Can't send signal to non-owned kernel")
            f = Future()
            f.set_result(None)
            return f

def waiting_for_reply(method):
    @wraps(method)
    def wrapped(self, *args, reply=True, timeout=None, **kwargs):
        if not reply:
            return method(self.loop_client, *args,  **kwargs)
        loop = self.loop_client.ioloop
        return loop.run_sync(lambda: method(self.loop_client, *args, **kwargs),
                                    timeout=timeout)

    if not method.__doc__:
        # python -OO removes docstrings,
        # so don't bother building the wrapped docstring
        return wrapped

    basedoc = method.__doc__.split('Returns\n', 1)[0]
    parts = [basedoc.strip()]
    if 'Parameters' not in basedoc:
        parts.append("""
        Parameters
        ----------
        """)
    parts.append("""
        reply: bool (default: True)
            Wait and return the reply. If False, return a tornado future.
        timeout: float or None (default: None)
            Timeout to use when waiting for a reply

        Returns
        -------
        msg_id: str
            The msg_id of the request sent, if reply=False (default)
        reply: dict
            The reply message for this request, if reply=True
    """)
    wrapped.__doc__ = '\n'.join(parts)
    return wrapped


class BlockingKernelClient:
    def __init__(self, connection_info, manager=None):
        self.connection_info = connection_info
        self.loop_client = IOLoopKernelClient(connection_info, manager)

    def close(self):
        self.loop_client.close()

    # Methods to send specific messages.
    # These requests run the IOLoop until their reply arrives
    execute = waiting_for_reply(IOLoopKernelClient.execute)
    complete = waiting_for_reply(IOLoopKernelClient.complete)
    inspect = waiting_for_reply(IOLoopKernelClient.inspect)
    history = waiting_for_reply(IOLoopKernelClient.history)
    kernel_info = waiting_for_reply(IOLoopKernelClient.kernel_info)
    comm_info = waiting_for_reply(IOLoopKernelClient.comm_info)
    shutdown = waiting_for_reply(IOLoopKernelClient.shutdown)
    is_complete = waiting_for_reply(IOLoopKernelClient.is_complete)
    interrupt = waiting_for_reply(IOLoopKernelClient.interrupt)
    shutdown_or_terminate = waiting_for_reply(IOLoopKernelClient.shutdown_or_terminate)

    def wait_for_ready(self, timeout=None):
        loop = self.loop_client.ioloop
        loop.run_sync(lambda: self.loop_client.wait_for_ready(), timeout=timeout)

    def input(self, string, parent=None):
        self.loop_client.input(string, parent=parent)

    allow_stdin = True

    def _stdin_hook_default(self, msg):
        """Handle an input request"""
        if msg.content.get('password', False):
            prompt = getpass
        else:
            prompt = input

        try:
            raw_data = prompt(msg.content["prompt"])
        except EOFError:
            # turn EOFError into EOF character
            raw_data = '\x04'
        except KeyboardInterrupt:
            sys.stdout.write('\n')
            return

        self.input(raw_data, parent=msg)

    def _output_hook_default(self, msg):
        """Default hook for redisplaying plain-text output"""
        msg_type = msg.header['msg_type']
        content = msg.content
        if msg_type == 'stream':
            stream = getattr(sys, content['name'])
            stream.write(content['text'])
        elif msg_type in ('display_data', 'execute_result'):
            sys.stdout.write(content['data'].get('text/plain', ''))
        elif msg_type == 'error':
            print('\n'.join(content['traceback']), file=sys.stderr)

    def _output_hook_kernel(self, session, socket, parent_header, msg):
        """Output hook when running inside an IPython kernel

        adds rich output support.
        """
        msg_type = msg['header']['msg_type']
        if msg_type in ('display_data', 'execute_result', 'error'):
            session.send(socket, msg_type, msg.content, parent=parent_header)
        else:
            self._output_hook_default(msg)

    def execute_interactive(self, code, silent=False, store_history=True,
                            user_expressions=None, allow_stdin=None,
                            stop_on_error=True,
                            timeout=None, output_hook=None, stdin_hook=None,
                            interrupt_timeout=None,
                            idle_timeout=4.0, raise_on_no_idle=False,
                            ):
        """Execute code in the kernel interactively

        Output will be redisplayed, and stdin prompts will be relayed as well.
        If an IPython kernel is detected, rich output will be displayed.

        You can pass a custom output_hook callable that will be called
        with every IOPub message that is produced instead of the default redisplay.

        .. versionadded:: 5.0

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

        timeout: float or None (default: None)
            Timeout to use when waiting for a reply

        output_hook: callable(msg)
            Function to be called with output messages.
            If not specified, output will be redisplayed.

        stdin_hook: callable(msg)
            Function to be called with stdin_request messages.
            If not specified, input/getpass will be called.

        Returns
        -------
        reply: dict
            The reply message for this request
        """
        if allow_stdin is None:
            allow_stdin = self.allow_stdin

        if stdin_hook is None:
            stdin_hook = self._stdin_hook_default
        if output_hook is None:
            # detect IPython kernel
            if 'IPython' in sys.modules:
                from IPython import get_ipython
                ip = get_ipython()
                in_kernel = getattr(ip, 'kernel', False)
                if in_kernel:
                    output_hook = partial(
                        self._output_hook_kernel,
                        ip.display_pub.session,
                        ip.display_pub.pub_socket,
                        ip.display_pub.parent_header,
                    )
        if output_hook is None:
            # default: redisplay plain-text outputs
            output_hook = self._output_hook_default

        self.loop_client.add_handler('stdin', stdin_hook)
        self.loop_client.add_handler('iopub', output_hook)

        try:
            return self.execute(
                code,
                silent=silent,
                store_history=store_history,
                user_expressions=user_expressions,
                allow_stdin=allow_stdin,
                stop_on_error=stop_on_error,
                timeout=timeout,
                interrupt_timeout=interrupt_timeout,
                idle_timeout=idle_timeout,
                raise_on_no_idle=raise_on_no_idle,
               )
        finally:
            self.loop_client.remove_handler('stdin', stdin_hook)
            self.loop_client.remove_handler('iopub', output_hook)


class ClientInThread(Thread):
    """Run an IOLoopKernelClient2 in a separate thread.

    The main client methods (execute, complete, etc.) all pass their arguments
    to the ioloop thread, which sends the messages. Handlers for received
    messages will be called in the ioloop thread, so they should typically
    use a signal or callback mechanism to interact with the application in
    the main thread.
    """
    client = None
    _exiting = False
    _ready_fut = None

    def __init__(self, connection_info, manager=None, loop=None):
        super(ClientInThread, self).__init__()
        self.daemon = True
        self.connection_info = connection_info
        self.manager = manager
        self.started = Event()
        self.kernel_responding = Event()

    @staticmethod
    @atexit.register
    def _notice_exit():
        ClientInThread._exiting = True

    def run(self):
        """Run my loop, ignoring EINTR events in the poller"""
        loop = ioloop.IOLoop(make_current=True)
        self.client = IOLoopKernelClient(self.connection_info, manager=self.manager)
        self.client.ioloop.add_callback(self.started.set)
        self._ready_fut = self.client.wait_for_ready()
        loop.add_future(self._ready_fut, lambda future: self.kernel_responding.set())
        try:
            self._run_loop()
        finally:
            self.client.close()
            self.client.ioloop.close()
            self.client = None

    def _run_loop(self):
        while True:
            try:
                self.client.ioloop.start()
            except ZMQError as e:
                if e.errno == errno.EINTR:
                    continue
                else:
                    raise
            except Exception:
                if self._exiting:
                    break
                else:
                    raise
            else:
                break

    def close(self):
        """Shut down the client and wait for the thread to exit.

        This closes the client's sockets and ioloop, and joins its thread.
        """
        if self.client is not None:
            self.client.ioloop.add_callback(self.client.ioloop.stop)
            self.join()

    @inherit_docstring(IOLoopKernelClient)
    def add_handler(self, channel, handler):
        self.client.handlers[channel].append(handler)

    @inherit_docstring(IOLoopKernelClient)
    def remove_handler(self, channel, handler):
        self.client.handlers[channel].remove(handler)

    def _send(self, channel, msg):
        self.client.ioloop.add_callback(self.client.messaging.send, channel, msg)

    # Client messaging methods --------------------------------
    # The sending is done in the IO thread, but we generate
    # the message in the calling thread so we can return the message ID.

    @inherit_docstring(KernelClient)
    def execute(self, code, silent=False, store_history=True,
                user_expressions=None, allow_stdin=None, stop_on_error=True):
        msg = execute_request(code, silent=silent, store_history=store_history,
              user_expressions=user_expressions, allow_stdin=allow_stdin,
              stop_on_error=stop_on_error)
        self._send('shell', msg)
        return msg.header['msg_id']

    @inherit_docstring(KernelClient)
    def complete(self, code, cursor_pos=None, _header=None):
        msg = complete_request(code, cursor_pos=cursor_pos)
        self._send('shell', msg)
        return msg.header['msg_id']

    @inherit_docstring(KernelClient)
    def inspect(self, code, cursor_pos=None, detail_level=0, _header=None):
        msg = inspect_request(code, cursor_pos=cursor_pos, detail_level=detail_level)
        self._send('shell', msg)
        return msg.header['msg_id']

    @inherit_docstring(KernelClient)
    def history(self, raw=True, output=False, hist_access_type='range',
                _header=None, **kwargs):
        msg = history_request(raw=raw, output=output,
                              hist_access_type=hist_access_type, **kwargs)
        self._send('shell', msg)
        return msg.header['msg_id']

    @inherit_docstring(KernelClient)
    def kernel_info(self, _header=None):
        msg = kernel_info_request()
        self._send('shell', msg)
        return msg.header['msg_id']

    @inherit_docstring(KernelClient)
    def comm_info(self, target_name=None, _header=None):
        msg = comm_info_request(target_name)
        self._send('shell', msg)
        return msg.header['msg_id']

    @inherit_docstring(KernelClient)
    def shutdown(self, restart=False, _header=None):
        msg = shutdown_request(restart)
        self._send('shell', msg)
        return msg.header['msg_id']

    @inherit_docstring(KernelClient)
    def is_complete(self, code, _header=None):
        msg = is_complete_request(code)
        self._send('shell', msg)
        return msg.header['msg_id']

    @inherit_docstring(KernelClient)
    def interrupt(self, _header=None):
        mode = self.connection_info.get('interrupt_mode', 'signal')
        if mode == 'message':
            msg = interrupt_request()
            self._send('shell', msg)
            return msg['header']['msg_id']
        elif self.owned_kernel:
            self.manager.interrupt()
        else:
            self.log.warning("Can't send signal to non-owned kernel")

    @inherit_docstring(KernelClient)
    def input(self, string, parent=None):
        msg = input_reply(string, parent=parent)
        self._send('stdin', msg)
