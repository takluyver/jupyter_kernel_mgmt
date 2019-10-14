"""Tests for KernelManager2"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import os

pjoin = os.path.join
import pytest
import signal
import sys
import time
from ipykernel.kernelspec import make_ipkernel_cmd
from jupyter_kernel_mgmt.subproc.async_manager import start_new_kernel
from .utils import skip_win32, setup_env
from ..util import maybe_future

TIMEOUT = 10

SIGNAL_KERNEL_CMD = [sys.executable, '-m', 'jupyter_kernel_mgmt.tests.signalkernel',
                         '-f', '{connection_file}']


@skip_win32
@pytest.mark.asyncio
async def test_signal_kernel_subprocesses(setup_env):
    km, kc = await start_new_kernel(SIGNAL_KERNEL_CMD, startup_timeout=TIMEOUT)
    try:
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
        reply = await maybe_future(fut)
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
    finally:
        kc.shutdown_or_terminate()
        kc.close()
        await km.kill()


@pytest.mark.asyncio
async def test_start_new_kernel(setup_env):
    km, kc = await start_new_kernel(make_ipkernel_cmd(), startup_timeout=TIMEOUT)
    try:
        is_alive = await km.is_alive()
        assert is_alive
    finally:
        kc.shutdown_or_terminate()
        kc.close()
        await km.kill()
