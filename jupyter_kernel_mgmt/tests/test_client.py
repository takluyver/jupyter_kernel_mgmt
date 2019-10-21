"""Tests for the KernelClient2"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.


import os
import pytest
pjoin = os.path.join

from ipykernel.kernelspec import make_ipkernel_cmd
from jupyter_protocol.messages import Message
from ..subproc.launcher import start_new_kernel
from .utils import run_sync

from IPython.utils.capture import capture_output

TIMEOUT = 30

# pytestmark = pytest.mark.asyncio
#
@pytest.fixture
def setup_test(setup_env):
    pytest.km, pytest.kc = start_new_kernel(kernel_cmd=make_ipkernel_cmd())
    yield pytest.km, pytest.kc
    pytest.kc.shutdown_or_terminate()
    pytest.kc.close()
    run_sync(pytest.km.kill())


def _check_reply(reply_type, reply):
    assert isinstance(reply, Message)
    assert reply.header['msg_type'] == reply_type + '_reply'
    assert reply.parent_header['msg_type'] == reply_type + '_request'


def test_execute_interactive(setup_test):
    kc = pytest.kc

    with capture_output() as io:
        reply = kc.execute_interactive("print('hello')", timeout=TIMEOUT)
    assert 'hello' in io.stdout
    assert reply.content['status'] == 'ok'


def test_history(setup_test):
    reply = pytest.kc.history(session=0)
    _check_reply('history', reply)


def test_inspect(setup_test):
    reply = pytest.kc.inspect('code')
    _check_reply('inspect', reply)


def test_complete(setup_test):
    reply = pytest.kc.complete('code')
    _check_reply('complete', reply)


def test_kernel_info(setup_test):
    reply = pytest.kc.kernel_info()
    _check_reply('kernel_info', reply)


def test_comm_info(setup_test):
    reply = pytest.kc.comm_info()
    _check_reply('comm_info', reply)


def test_shutdown(setup_test):
    reply = pytest.kc.shutdown()
    _check_reply('shutdown', reply)