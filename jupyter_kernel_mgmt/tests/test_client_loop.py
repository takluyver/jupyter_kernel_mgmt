"""Tests for the ioloop KernelClient running in a separate thread."""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import pytest

from async_generator import yield_, async_generator
from jupyter_protocol.messages import Message
from ..discovery import KernelFinder, IPykernelProvider
from jupyter_kernel_mgmt import run_kernel_async

TIMEOUT = 30

pytestmark = pytest.mark.asyncio

@pytest.fixture
@async_generator
async def kernel_client(setup_env):
    # Start a client in a new thread, put received messages in queues.
    # Instantiate KernelFinder directly, so tests aren't affected by entrypoints
    # from other installed packages
    finder = KernelFinder([IPykernelProvider()])
    async with run_kernel_async('pyimport/kernel', finder=finder) as kc:
        await yield_(kc)


def _check_reply(reply_type, reply):
    assert isinstance(reply, Message)
    assert reply.header['msg_type'] == reply_type + '_reply'
    assert reply.parent_header['msg_type'] == reply_type + '_request'


async def test_history(kernel_client):
    reply = await kernel_client.history(session=0)
    _check_reply('history', reply)


async def test_inspect(kernel_client):
    reply = await kernel_client.inspect('who cares')
    _check_reply('inspect', reply)


async def test_complete(kernel_client):
    reply = await kernel_client.complete('who cares')
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
