from .test_discovery import DummyKernelManager, DummyKernelProvider

from jupyter_kernel_mgmt import discovery
from jupyter_kernel_mgmt.restarter import KernelRestarterBase

def test_reinstantiate():
    # If the kernel fails, a new manager should be instantiated
    kf = discovery.KernelFinder(providers=[DummyKernelProvider()])
    _, manager = kf.launch('dummy/sample')
    manager.kill()

    restarter = KernelRestarterBase(manager, 'dummy/sample', kernel_finder=kf)
    assert restarter.kernel_manager is manager
    restarter.poll()
    assert restarter.kernel_manager is not manager
    assert restarter.kernel_manager.is_alive()
