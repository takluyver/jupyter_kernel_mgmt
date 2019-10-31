"""Tests for the KernelClient2"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.


import os
import pytest
pjoin = os.path.join
from async_generator import yield_, async_generator
from ipykernel.kernelspec import make_ipkernel_cmd
from jupyter_protocol.messages import Message
from ..subproc.launcher import start_new_kernel

from IPython.utils.capture import capture_output

TIMEOUT = 30

pytestmark = pytest.mark.asyncio

@pytest.fixture
@async_generator
async def kernel_client(setup_env):
    km, kc = await start_new_kernel(kernel_cmd=make_ipkernel_cmd())
    await yield_(kc)
    kc.shutdown_or_terminate()
    kc.close()
    await km.kill()


def _check_reply(reply_type, reply):
    assert isinstance(reply, Message)
    assert reply.header['msg_type'] == reply_type + '_reply'
    assert reply.parent_header['msg_type'] == reply_type + '_request'


@pytest.mark.xfail(AssertionError, reason="IOLoopKernelClient doesn't have execute_interactive - calling execute")
async def test_execute_interactive(kernel_client):
    with capture_output() as io:
        # reply = await kernel_client.execute_interactive("print('hello')", timeout=TIMEOUT)
        reply = await kernel_client.execute("print('hello')")
    assert reply.content['status'] == 'ok'
    assert 'hello' in io.stdout   # output capture doesn't appear to work with just 'execute'


async def test_history(kernel_client):
    reply = await kernel_client.history(session=0)
    _check_reply('history', reply)


async def test_inspect(kernel_client):
    reply = await kernel_client.inspect('code')
    _check_reply('inspect', reply)


async def test_complete(kernel_client):
    reply = await kernel_client.complete('code')
    _check_reply('complete', reply)


async def test_kernel_info(kernel_client):
    reply = await kernel_client.kernel_info()
    _check_reply('kernel_info', reply)


async def test_comm_info(kernel_client):
    reply = await kernel_client.comm_info()
    _check_reply('comm_info', reply)


async def test_shutdown(kernel_client):
    reply = await kernel_client.shutdown()
    _check_reply('shutdown', reply)