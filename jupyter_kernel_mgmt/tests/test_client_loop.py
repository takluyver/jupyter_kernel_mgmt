"""Tests for the ioloop KernelClient running in a separate thread."""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import os
import pytest
try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty

pjoin = os.path.join

from async_generator import yield_, async_generator
from ipykernel.kernelspec import make_ipkernel_cmd
from jupyter_protocol.messages import Message
from jupyter_kernel_mgmt.subproc.async_manager import (
    AsyncSubprocessKernelLauncher, start_new_kernel
)
from jupyter_kernel_mgmt.client import ClientInThread

from ipython_genutils.py3compat import string_types

TIMEOUT = 30

pytestmark = pytest.mark.asyncio

@pytest.fixture
@async_generator
async def setup_test(setup_env):

    # Start a client in a new thread, put received messages in queues.
    launcher = AsyncSubprocessKernelLauncher(make_ipkernel_cmd(), cwd='.')
    connection_info, km = await launcher.launch()
    pytest.kc = ClientInThread(connection_info, manager=km)
    pytest.received = {'shell': Queue(), 'iopub': Queue()}
    pytest.kc.start()
    if not pytest.kc.kernel_responding.wait(10.0):
        raise RuntimeError("Failed to start kernel client")
    pytest.kc.add_handler(_queue_msg, {'shell', 'iopub'})
    await yield_(pytest.kc)
    pytest.kc.shutdown()
    pytest.kc.close()
    await km.kill()


def _queue_msg(msg, channel):
    pytest.received[channel].put(msg)


def _check_reply(reply_type, reply):
    assert isinstance(reply, Message)
    assert reply.header['msg_type'] == reply_type + '_reply'
    assert reply.parent_header['msg_type'] == reply_type + '_request'


async def test_history(setup_test):
    kc = pytest.kc
    msg_id = kc.history(session=0)
    assert isinstance(msg_id, string_types)
    reply = pytest.received['shell'].get(timeout=TIMEOUT)
    _check_reply('history', reply)


async def test_inspect(setup_test):
    kc = pytest.kc
    msg_id = kc.inspect('who cares')
    assert isinstance(msg_id, string_types)
    reply = pytest.received['shell'].get(timeout=TIMEOUT)
    _check_reply('inspect', reply)


async def test_complete(setup_test):
    kc = pytest.kc
    msg_id = kc.complete('who cares')
    assert isinstance(msg_id, string_types)
    reply = pytest.received['shell'].get(timeout=TIMEOUT)
    _check_reply('complete', reply)


async def test_kernel_info(setup_test):
    kc = pytest.kc
    msg_id = kc.kernel_info()
    assert isinstance(msg_id, string_types)
    reply = pytest.received['shell'].get(timeout=TIMEOUT)
    _check_reply('kernel_info', reply)


async def test_comm_info(setup_test):
    kc = pytest.kc
    msg_id = kc.comm_info()
    assert isinstance(msg_id, string_types)
    reply = pytest.received['shell'].get(timeout=TIMEOUT)
    _check_reply('comm_info', reply)


async def test_shutdown(setup_test):
    kc = pytest.kc
    msg_id = kc.shutdown()
    assert isinstance(msg_id, string_types)
    reply = pytest.received['shell'].get(timeout=TIMEOUT)
    _check_reply('shutdown', reply)
