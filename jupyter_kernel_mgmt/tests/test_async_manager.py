import os
import pytest
from unittest import TestCase

asyncio = pytest.importorskip('asyncio')

from ipykernel.kernelspec import make_ipkernel_cmd
from .utils import test_env
from jupyter_kernel_mgmt.subproc.async_manager import (
    AsyncSubprocessKernelLauncher, start_new_kernel
)

TIMEOUT = 10

# noinspection PyCompatibility
class TestKernelManager(TestCase):
    def setUp(self):
        self.env_patch = test_env()
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()

    async def t_get_connect_info(self):
        launcher = AsyncSubprocessKernelLauncher(make_ipkernel_cmd(), os.getcwd())
        info, km = await launcher.launch()
        try:
            self.assertEqual(set(info.keys()), {
                'ip', 'transport',
                'hb_port', 'shell_port', 'stdin_port', 'iopub_port', 'control_port',
                'key', 'signature_scheme',
            })
        finally:
            await km.kill()
            await km.cleanup()

    def test_get_connect_info(self):
        asyncio.get_event_loop().run_until_complete(self.t_get_connect_info())

    async def t_start_new_kernel(self):
        km, kc = await start_new_kernel(make_ipkernel_cmd(), startup_timeout=TIMEOUT)
        try:
            self.assertTrue((await km.is_alive()))
            self.assertTrue(kc.is_alive())
        finally:
            kc.shutdown_or_terminate()
            kc.close()

    def test_start_new_kernel(self):
        asyncio.get_event_loop().run_until_complete(self.t_start_new_kernel())
