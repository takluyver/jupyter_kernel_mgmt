"""Tests for KernelManager2"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import os

pjoin = os.path.join
import signal
import sys
import time
from tornado.ioloop import IOLoop
from unittest import TestCase

from ipykernel.kernelspec import make_ipkernel_cmd
from jupyter_kernel_mgmt.subproc.launcher import run_kernel,  start_new_kernel
from .utils import test_env, skip_win32

TIMEOUT = 30

SIGNAL_KERNEL_CMD = [sys.executable, '-m', 'jupyter_client.tests.signalkernel',
                         '-f', '{connection_file}']

class TestKernelManager(TestCase):
    def setUp(self):
        self.env_patch = test_env()
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()

    @skip_win32
    def test_signal_kernel_subprocesses(self):
        with run_kernel(SIGNAL_KERNEL_CMD, startup_timeout=5) as kc:
            def execute(cmd):
                reply = kc.execute(cmd)
                content = reply.content
                self.assertEqual(content['status'], 'ok')
                return content

            N = 5
            for i in range(N):
                execute("start")
            time.sleep(1)  # make sure subprocs stay up
            reply = execute('check')
            self.assertEqual(reply['user_expressions']['poll'], [None] * N)

            # start a job on the kernel to be interrupted
            fut = kc.execute('sleep', reply=False)
            time.sleep(1)  # ensure sleep message has been handled before we interrupt
            kc.interrupt()
            reply = IOLoop.current().run_sync(lambda: fut)
            content = reply.content
            self.assertEqual(content['status'], 'ok')
            self.assertEqual(content['user_expressions']['interrupted'], True)
            # wait up to 5s for subprocesses to handle signal
            for i in range(50):
                reply = execute('check')
                if reply['user_expressions']['poll'] != [-signal.SIGINT] * N:
                    time.sleep(0.1)
                else:
                    break
            # verify that subprocesses were interrupted
            self.assertEqual(reply['user_expressions']['poll'],
                             [-signal.SIGINT] * N)

    def test_start_new_kernel(self):
        km, kc = start_new_kernel(make_ipkernel_cmd(), startup_timeout=5)
        try:
            self.assertTrue(km.is_alive())
        finally:
            kc.shutdown_or_terminate()
