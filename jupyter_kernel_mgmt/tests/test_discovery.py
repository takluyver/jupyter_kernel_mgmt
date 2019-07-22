import sys
import unittest

from os.path import join as pjoin
from jupyter_kernel_mgmt import discovery, kernelspec
from jupyter_kernel_mgmt.managerabc import KernelManagerABC
from jupyter_kernel_mgmt.subproc.manager import KernelManager
from jupyter_core import paths
from .utils import test_env
from .test_kernelspec import install_sample_kernel


class DummyKernelProvider(discovery.KernelProviderBase):
    """A dummy kernel provider for testing KernelFinder"""
    id = 'dummy'

    def find_kernels(self):
        yield 'sample', {'argv': ['dummy_kernel']}

    def launch(self, name, cwd=None):
        return {}, DummyKernelManager()

    def launch_async(self, name, cwd=None):
        pass


class DummyKernelSpecProvider(discovery.KernelSpecProvider):
    """A dummy kernelspec provider subclass for testing KernelFinder and KernelSpecProvider subclasses"""
    id = 'dummy_kspec'
    kernel_file = 'dummy_kspec.json'

    # find_kernels() is inherited from KernelsSpecProvider

    def launch(self, name, cwd=None):
        return {}, DummyKernelManager()


class DummyKernelManager(KernelManagerABC):
    _alive = True

    def is_alive(self):
        """Check whether the kernel is currently alive (e.g. the process exists)
        """
        return self._alive

    def wait(self, timeout):
        """Wait for the kernel process to exit.
        """
        return False

    def signal(self, signum):
        """Send a signal to the kernel."""
        pass

    def interrupt(self):
        pass

    def kill(self):
        self._alive = False

    def get_connection_info(self):
        """Return a dictionary of connection information"""
        return {}


class KernelDiscoveryTests(unittest.TestCase):

    def setUp(self):
        self.env_patch = test_env()
        self.env_patch.start()
        self.sample_kernel_dir = install_sample_kernel(
            pjoin(paths.jupyter_data_dir(), 'kernels'))
        self.prov_sample1_kernel_dir = install_sample_kernel(
            pjoin(paths.jupyter_data_dir(), 'kernels'), 'dummy_kspec1', 'dummy_kspec.json')
        self.prov_sample2_kernel_dir = install_sample_kernel(
            pjoin(paths.jupyter_data_dir(), 'kernels'), 'dummy_kspec2', 'dummy_kspec.json')

    def tearDown(self):
        self.env_patch.stop()

    @staticmethod
    def test_ipykernel_provider():
        import ipykernel  # Fail clearly if ipykernel not installed
        ikf = discovery.IPykernelProvider()

        res = list(ikf.find_kernels())
        assert len(res) == 1, res
        name, info = res[0]
        assert name == 'kernel'
        assert info['argv'][0] == sys.executable

    @staticmethod
    def test_meta_kernel_finder():
        kf = discovery.KernelFinder(providers=[DummyKernelProvider()])
        assert list(kf.find_kernels()) == \
            [('dummy/sample', {'argv': ['dummy_kernel']})]

        conn_info, manager = kf.launch('dummy/sample')
        assert isinstance(manager, DummyKernelManager)

    def test_kernel_spec_provider(self):
        kf = discovery.KernelFinder(providers=[discovery.KernelSpecProvider()])

        dummy_kspecs = list(kf.find_kernels())

        count = 0
        found_argv = []
        for name, spec in dummy_kspecs:
            if name == 'spec/sample':
                found_argv = spec['argv']
                count += 1

        assert count == 1
        assert found_argv == ['cat', '{connection_file}']

        with self.assertRaises(kernelspec.NoSuchKernel):
            kf.launch('spec/dummy_kspec1')

        conn_info, manager = kf.launch('spec/sample')
        assert isinstance(manager, KernelManager)
        # this actually starts a kernel, so let's make sure its terminated
        manager.kill()

    @staticmethod
    def test_kernel_spec_provider_subclass():
        kf = discovery.KernelFinder(providers=[DummyKernelSpecProvider()])

        dummy_kspecs = list(kf.find_kernels())
        assert len(dummy_kspecs) == 2

        for name, spec in dummy_kspecs:
            assert name.startswith('dummy_kspec/dummy_kspec')
            assert spec['argv'] == ['cat', '{connection_file}']

        conn_info, manager = kf.launch('dummy_kspec/dummy_kspec1')
        assert isinstance(manager, DummyKernelManager)
