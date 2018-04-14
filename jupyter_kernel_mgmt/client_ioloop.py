import atexit
import errno
from functools import partial
from threading import Thread, Event
from tornado.concurrent import Future
from zmq import ZMQError
from zmq.eventloop import ioloop, zmqstream

from .client import KernelClient
from .util import inherit_docstring


class ErrorInKernel(Exception):
    def __init__(self, ename, evalue, traceback):
        self.ename = ename
        self.evalue = evalue
        self.traceback = traceback

    def __str__(self):
        return '\n'.join(self.traceback
                         + ['{}: {}'.format(self.ename,  self.evalue)])

class IOLoopKernelClient(KernelClient):
    """Uses a zmq/tornado IOLoop to handle received messages and fire callbacks.

    Use ClientInThread to run this in a separate thread alongside your
    application.
    """
    def __init__(self, connection_info, **kwargs):
        super(IOLoopKernelClient, self).__init__(connection_info, **kwargs)
        self.ioloop = ioloop.IOLoop.current()
        self.request_futures = {}
        self.handlers = {
            'iopub': [],
            'shell': [self._auto_adapt, self._fulfil_request],
            'stdin': [],
            'control': [self._fulfil_request],
        }
        self.streams = {}
        for channel, socket in self.messaging.sockets.items():
            self.streams[channel] = s = zmqstream.ZMQStream(socket, self.ioloop)
            s.on_recv(partial(self._handle_recv, channel))

    def close(self):
        """Close the client's sockets & streams.

        This does not close the IOLoop.
        """
        for stream in self.streams.values():
            stream.close()
        if self.hb_monitor:
            self.hb_monitor.stop()

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
            if parent_future:
                if msg.content.get('status', 'ok') == 'error':
                    e = ErrorInKernel(msg.content.get('ename', 'ERROR'),
                                      msg.content.get('evalue', ''),
                                      msg.content.get('traceback', [])
                                     )
                    parent_future.set_exception(e)
                else:
                    parent_future.set_result(msg)

    def _handle_recv(self, channel, msg):
        """Callback for stream.on_recv.

        Unpacks message, and calls handlers with it.
        """
        ident, smsg = self.session.feed_identities(msg)
        msg = self.session.deserialize(smsg)
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
    def execute(self, code, silent=False, store_history=True,
                user_expressions=None, allow_stdin=None, stop_on_error=True,
                _header=None):
        msg_id = super().execute(code, silent=silent, store_history=store_history,
              user_expressions=user_expressions, allow_stdin=allow_stdin,
              stop_on_error=stop_on_error, _header=_header)
        return self._request_future(msg_id)

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
        return self._request_future(msg_id)

    def comm_info(self, target_name=None, _header=None):
        msg_id = super().comm_info(target_name, _header=_header)
        return self._request_future(msg_id)

    def shutdown(self, restart=False, _header=None):
        msg_id = super().shutdown(restart, _header=_header)
        return self._request_future(msg_id)

    def is_complete(self, code, _header=None):
        """Ask the kernel whether some code is complete and ready to execute."""
        msg_id = super().is_complete(code, _header=_header)
        return self._request_future(msg_id)

    def interrupt(self, _header=None):
        """Send an interrupt message/signal to the kernel"""
        mode = self.connection_info.get('interrupt_mode', 'signal')
        if mode == 'message':
            msg_id = super().interrupt()
            return self._request_future(msg_id, _header=_header)
        elif self.owned_kernel:
            self.manager.interrupt()
        else:
            self.log.warning("Can't send signal to non-owned kernel")

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

    def __init__(self, connection_info, manager=None, loop=None):
        super(ClientInThread, self).__init__()
        self.daemon = True
        self.connection_info = connection_info
        self.manager = manager
        self.started = Event()

    @staticmethod
    @atexit.register
    def _notice_exit():
        ClientInThread._exiting = True

    def run(self):
        """Run my loop, ignoring EINTR events in the poller"""
        loop = ioloop.IOLoop(make_current=True)
        self.client = IOLoopKernelClient(self.connection_info, manager=self.manager)
        self.client.ioloop.add_callback(self.started.set)
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

    @property
    def ioloop(self):
        if self.client:
            return self.client.ioloop

    def close(self):
        """Shut down the client and wait for the thread to exit.

        This closes the client's sockets and ioloop, and joins its thread.
        """
        if self.client is not None:
            self.ioloop.add_callback(self.client.ioloop.stop)
            self.join()

    @inherit_docstring(IOLoopKernelClient)
    def add_handler(self, channel, handler):
        self.client.handlers[channel].append(handler)

    @inherit_docstring(IOLoopKernelClient)
    def remove_handler(self, channel, handler):
        self.client.handlers[channel].remove(handler)

    # Client messaging methods --------------------------------
    # These send as much work as possible to the IO thread, but we generate
    # the header in the calling thread so we can return the message ID.

    @inherit_docstring(KernelClient)
    def execute(self, *args, **kwargs):
        hdr = self.client.session.msg_header('execute_request')
        self.ioloop.add_callback(self.client.execute, *args, _header=hdr, **kwargs)
        return hdr['msg_id']

    @inherit_docstring(KernelClient)
    def complete(self, *args, **kwargs):
        hdr = self.client.session.msg_header('complete_request')
        self.ioloop.add_callback(self.client.complete, *args, _header=hdr, **kwargs)
        return hdr['msg_id']

    @inherit_docstring(KernelClient)
    def inspect(self, *args, **kwargs):
        hdr = self.client.session.msg_header('inspect_request')
        self.ioloop.add_callback(self.client.inspect, *args, _header=hdr, **kwargs)
        return hdr['msg_id']

    @inherit_docstring(KernelClient)
    def history(self, *args, **kwargs):
        hdr = self.client.session.msg_header('history_request')
        self.ioloop.add_callback(self.client.history, *args, _header=hdr, **kwargs)
        return hdr['msg_id']

    @inherit_docstring(KernelClient)
    def kernel_info(self, _header=None):
        hdr = self.client.session.msg_header('kernel_info_request')
        self.ioloop.add_callback(self.client.kernel_info, _header=hdr)
        return hdr['msg_id']

    @inherit_docstring(KernelClient)
    def comm_info(self, target_name=None, _header=None):
        hdr = self.client.session.msg_header('comm_info_request')
        self.ioloop.add_callback(self.client.comm_info, target_name, _header=hdr)
        return hdr['msg_id']

    @inherit_docstring(KernelClient)
    def shutdown(self, restart=False, _header=None):
        hdr = self.client.session.msg_header('shutdown_request')
        self.ioloop.add_callback(self.client.shutdown, restart, _header=hdr)
        return hdr['msg_id']

    @inherit_docstring(KernelClient)
    def is_complete(self, code, _header=None):
        hdr = self.client.session.msg_header('is_complete_request')
        self.ioloop.add_callback(self.client.is_complete, code, _header=hdr)
        return hdr['msg_id']

    @inherit_docstring(KernelClient)
    def interrupt(self, _header=None):
        mode = self.connection_info.get('interrupt_mode', 'signal')
        if mode == 'message':
            hdr = self.client.session.msg_header('is_complete_request')
            self.ioloop.add_callback(self.client.interrupt, _header=hdr)
            return hdr['msg_id']
        else:
            self.client.interrupt()

    @inherit_docstring(KernelClient)
    def input(self, string, parent=None):
        self.ioloop.add_callback(self.client.is_complete, string, parent=parent)
