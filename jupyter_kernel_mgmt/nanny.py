import json
from jupyter_core.paths import jupyter_runtime_dir
from jupyter_core.utils import ensure_dir_exists
from jupyter_protocol.sockets import NannyMessaging
from jupyter_protocol.messages import Message
import os
import sys
from tornado.ioloop import PeriodicCallback, IOLoop
from zmq.eventloop.zmqstream import ZMQStream

from .discovery import KernelFinder
from .subproc.launcher import set_sticky_bit

class KernelNanny:
    def __init__(self, connection_info, manager):
        self.connection_info = connection_info
        self.manager = manager
        self.messaging = NannyMessaging(connection_info)
        self.connection_file = self.write_connection_file()
        self.control_stream = ZMQStream(self.messaging.control_socket)
        self.control_stream.on_recv(self.handle_request)
        self.kernel_poller = PeriodicCallback(self.poll_kernel, 1000)

    def write_connection_file(self):
        runtime_dir = jupyter_runtime_dir()
        ensure_dir_exists(runtime_dir)
        fname = os.path.join(runtime_dir, 'kernelnanny-%s.json' % os.getpid())

        with open(fname, 'w') as f:
            f.write(json.dumps(self.connection_info, indent=2))

        set_sticky_bit(fname)
        return fname

    def cleanup(self):
        self.messaging.close()
        os.unlink(self.connection_file)

    allowed_requests = {
        'interrupt_request': 'interrupt_reply',
        'is_alive_request': 'is_alive_reply',
    }

    def handle_request(self, raw_msg):
        msg = self.messaging.session.deserialize(raw_msg)
        msg_type = msg.header['msg_type']
        if msg_type not in self.allowed_requests:
            raise ValueError("Unknown request type: {!r}".format(msg_type))

        reply_type = self.allowed_requests[msg_type]
        reply_content = getattr(self, msg_type)(msg)
        reply = Message.from_type(reply_type, reply_content, parent_msg=msg)
        self.messaging.send('nanny_control', reply)

    def interrupt_request(self, msg):
        self.manager.interrupt()
        return {}

    def is_alive_request(self, msg):
        return {'alive': self.manager.is_alive()}

    def poll_kernel(self):
        if not self.manager.is_alive():
            self.on_kernel_dead()

    def on_kernel_dead(self):
        msg = Message.from_type('kernel_died', {})
        self.messaging.send('nanny_events', msg)
        IOLoop.current().stop()

def main():
    kf = KernelFinder.from_entrypoints()
    print("Launching kernel", sys.argv[1])
    conn_info, mgr = kf.launch(sys.argv[1])
    nanny = KernelNanny(conn_info, mgr)

    loop = IOLoop.current()
    try:
        loop.start()
    except KeyboardInterrupt:
        print("Interrupted, stopping kernel")
        mgr.kill()
    finally:
        loop.close()
        mgr.cleanup()
        nanny.cleanup()

if __name__ == '__main__':
    main()
