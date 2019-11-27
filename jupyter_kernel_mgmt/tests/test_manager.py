"""Tests for KernelManager2"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import asyncio
from async_generator import async_generator, yield_
import os

pjoin = os.path.join
import pytest
import signal
import sys
import time
from jupyter_kernel_mgmt.subproc import SubprocessKernelLauncher
from jupyter_kernel_mgmt.client import IOLoopKernelClient

TIMEOUT = 10

SIGNAL_KERNEL_CMD = [sys.executable, '-m', 'jupyter_kernel_mgmt.tests.signalkernel',
                         '-f', '{connection_file}']

@pytest.fixture
@async_generator
async def signal_kernel_client(setup_env):
    skl = SubprocessKernelLauncher(SIGNAL_KERNEL_CMD, cwd=os.getcwd())
    conn_info, km = await skl.launch()
    kc = IOLoopKernelClient(conn_info, km)
    try:
        await asyncio.wait_for(kc.wait_for_ready(), timeout=60)
        await yield_(kc)
    finally:
        await kc.shutdown_or_terminate()
        kc.close()


@pytest.mark.skipif(sys.platform.startswith('win'), reason="Windows")
@pytest.mark.asyncio
async def test_signal_kernel_subprocesses(signal_kernel_client):
    kc = signal_kernel_client
    async def execute(cmd):
        reply = await kc.execute(cmd)
        content = reply.content
        assert content['status'] == 'ok'
        return content

    N = 5
    for i in range(N):
        await execute("start")
    time.sleep(1)  # make sure subprocs stay up
    reply = await execute('check')
    assert reply['user_expressions']['poll'] == ([None] * N)

    # start a job on the kernel to be interrupted
    fut = kc.execute('sleep')
    time.sleep(1)  # ensure sleep message has been handled before we interrupt
    await kc.interrupt()
    reply = await fut
    content = reply.content
    assert content['status'] == 'ok'
    assert content['user_expressions']['interrupted']
    # wait up to 5s for subprocesses to handle signal
    for i in range(50):
        reply = await execute('check')
        if reply['user_expressions']['poll'] != [-signal.SIGINT] * N:
            time.sleep(0.1)
        else:
            break
    # verify that subprocesses were interrupted
    assert reply['user_expressions']['poll'] == ([-signal.SIGINT] * N)
