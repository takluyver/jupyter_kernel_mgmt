import asyncio
from .test_discovery import DummyKernelManager, DummyKernelProvider

from jupyter_kernel_mgmt import discovery
from jupyter_kernel_mgmt.restarter import KernelRestarterBase


async def t_reinstantiate():
    # If the kernel fails, a new manager should be instantiated
    kf = discovery.KernelFinder(providers=[DummyKernelProvider()])
    _, manager = await kf.launch('dummy/sample')
    await manager.kill()

    restarter = KernelRestarterBase(manager, 'dummy/sample', kernel_finder=kf)
    assert restarter.kernel_manager is manager
    await restarter.poll()
    assert restarter.kernel_manager is not manager
    assert await restarter.kernel_manager.is_alive()


def test_reinstantiate():
    asyncio.get_event_loop().run_until_complete(t_reinstantiate())
