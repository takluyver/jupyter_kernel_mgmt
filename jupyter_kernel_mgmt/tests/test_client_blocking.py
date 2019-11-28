"""Tests for BlockingKernelClient"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import pytest
from jupyter_protocol.messages import Message
from ..discovery import KernelFinder, IPykernelProvider
from jupyter_kernel_mgmt import run_kernel_blocking

from IPython.utils.capture import capture_output

TIMEOUT = 30

@pytest.fixture
def kernel_client(setup_env):
    # Instantiate KernelFinder directly, so tests aren't affected by entrypoints
    # from other installed packages
    finder = KernelFinder([IPykernelProvider()])
    with run_kernel_blocking('pyimport/kernel', finder=finder) as kc:
        yield kc


def _check_reply(reply_type, reply):
    assert isinstance(reply, Message)
    assert reply.header['msg_type'] == reply_type + '_reply'
    assert reply.parent_header['msg_type'] == reply_type + '_request'


def test_execute_interactive(kernel_client):
    with capture_output() as io:
        reply = kernel_client.execute_interactive("print('hello')", timeout=TIMEOUT)
    assert reply.content['status'] == 'ok'
    assert 'hello' in io.stdout   # output capture doesn't appear to work with just 'execute'


def test_history(kernel_client):
    reply = kernel_client.history(session=0)
    _check_reply('history', reply)


def test_inspect(kernel_client):
    reply = kernel_client.inspect('code')
    _check_reply('inspect', reply)


def test_complete(kernel_client):
    reply = kernel_client.complete('code')
    _check_reply('complete', reply)


def test_kernel_info(kernel_client):
    reply = kernel_client.kernel_info()
    _check_reply('kernel_info', reply)


def test_comm_info(kernel_client):
    reply = kernel_client.comm_info()
    _check_reply('comm_info', reply)


def test_shutdown(kernel_client):
    reply = kernel_client.shutdown()
    _check_reply('shutdown', reply)
