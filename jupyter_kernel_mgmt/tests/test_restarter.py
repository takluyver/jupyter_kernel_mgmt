"""Tests for Kernel Restarts"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import pytest

from .test_discovery import DummyKernelProvider

from jupyter_kernel_mgmt import discovery
from jupyter_kernel_mgmt.restarter import KernelRestarterBase


@pytest.mark.asyncio
async def test_reinstantiate(setup_env):
    # If the kernel fails, a new manager should be instantiated
    kf = discovery.KernelFinder(providers=[DummyKernelProvider()])
    _, manager = await kf.launch('dummy/sample')
    await manager.kill()

    restarter = KernelRestarterBase(manager, 'dummy/sample', kernel_finder=kf)
    assert restarter.kernel_manager is manager
    await restarter.poll()
    assert restarter.kernel_manager is not manager
    assert await restarter.kernel_manager.is_alive()

