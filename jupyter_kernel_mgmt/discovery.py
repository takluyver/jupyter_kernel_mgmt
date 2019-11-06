from abc import ABCMeta, abstractmethod
import asyncio
import entrypoints
import logging
import six
from tornado.concurrent import Future
from traitlets.config import Application
try:
    from json import JSONDecodeError
except ImportError:
    # JSONDecodeError is new in Python 3.5, so while we support 3.4:
    JSONDecodeError = ValueError

from .kernelspec import KernelSpecManager, KernelSpec
from .subproc import SubprocessKernelLauncher
from .util import run_sync

log = logging.getLogger(__name__)


class KernelProviderBase(six.with_metaclass(ABCMeta, object)):
    id = None  # Should be a short string identifying the provider class.

    @abstractmethod
    @asyncio.coroutine
    def find_kernels(self):
        """Return an iterator of (kernel_name, kernel_info_dict) tuples."""
        pass

    @abstractmethod
    async def launch(self, name, cwd=None, launch_params=None):
        """
        Launch a kernel, returns a 2-tuple of (connection_info, kernel_manager).

        **name** will be one of the kernel names produced by find_kernels() and
        known to this provider.

        **cwd** (optional) a string that specifies the path to the current directory of the
        notebook as conveyed by the client.  Its interpretation is provider-specific.

        **launch_params** (optional) a dictionary consisting of the launch parameters used
        to launch the kernel.  Its interpretation is provider-specific.

        This method launches and manages the kernel in an asynchronous (non-blocking) manner.
        """
        pass

    def load_config(self, config=None):
        """
        Loads the configuration corresponding to the hosting application.  This method
        is called during KernelFinder initialization prior to any other methods.
        The Kernel provider is responsible for interpreting the `config` parameter
        (when present).

        **config** (optional) an instance of `Config
        <https://traitlets.readthedocs.io/en/stable/config.html#the-main-concepts>`_
        consisting of the hosting application's configurable traitlets.
        """
        pass


class KernelSpecProvider(KernelProviderBase):
    """Offers kernel types from installed kernelspec directories.
    """
    id = 'spec'
    kernel_file = 'kernel.json'

    def __init__(self, search_path=None):
        self.ksm = KernelSpecManager(kernel_dirs=search_path, kernel_file=self.kernel_file)

    @asyncio.coroutine
    def find_kernels(self):
        for name, resdir in self.ksm.find_kernel_specs().items():
            try:
                spec = KernelSpec.from_resource_dir(resdir, kernel_file=self.kernel_file)
            except JSONDecodeError:
                log.warning("Failed to parse kernelspec in %s", resdir)
                continue

            yield name, {
                # TODO: get full language info
                'language_info': {'name': spec.language},
                'display_name': spec.display_name,
                'argv': spec.argv,
                'resource_dir': spec.resource_dir,
                'metadata': spec.metadata,
            }

    async def launch(self, name, cwd=None, launch_params=None):
        spec = self.ksm.get_kernel_spec(name)
        return await SubprocessKernelLauncher(
            kernel_cmd=spec.argv, extra_env=spec.env, cwd=cwd, launch_params=launch_params).launch()


class IPykernelProvider(KernelProviderBase):
    """
    Offers a kernel type using the Python interpreter it's running in.
    This checks if ipykernel is importable first.  If import fails, it doesn't offer a kernel type.
    """
    id = 'pyimport'

    def _check_for_kernel(self):
        try:
            from ipykernel.kernelspec import RESOURCES, get_kernel_dict
            from ipykernel.ipkernel import IPythonKernel
        except ImportError:
            return None
        else:
            return {
                'spec': get_kernel_dict(),
                'language_info': IPythonKernel.language_info,
                'resource_dir': RESOURCES,
            }

    @asyncio.coroutine
    def find_kernels(self):
        info = self._check_for_kernel()

        if info:
            yield 'kernel', {
                'language_info': info['language_info'],
                'display_name': info['spec']['display_name'],
                'argv': info['spec']['argv'],
                'resource_dir': info['resource_dir'],
            }

    async def launch(self, name, cwd=None, launch_params=None):
        info = self._check_for_kernel()
        if info is None:
            raise Exception("ipykernel is not importable")
        return await SubprocessKernelLauncher(
            kernel_cmd=info['spec']['argv'], extra_env={}, cwd=cwd, launch_params=launch_params).launch()


class KernelFinder(object):
    """
    Manages a collection of kernel providers to find available kernel types.
    *providers* should be a list of kernel provider instances.
    """
    def __init__(self, providers):
        self.providers = providers

        # If there's an application singleton, pass its configurables to the provider.  If
        # no application, still give provider a chance to handle configuration loading.
        config = None
        if Application.initialized():
            config = Application.instance().config

        for provider in providers:
            provider.load_config(config=config)

    @classmethod
    def from_entrypoints(cls):
        """
        Load all kernel providers advertised by entry points.

        Kernel providers should use the "jupyter_kernel_mgmt.kernel_type_providers"
        entry point group.

        Returns an instance of KernelFinder.
        """
        providers = []
        for ep in entrypoints.get_group_all('jupyter_kernel_mgmt.kernel_type_providers'):
            try:
                provider = ep.load()()  # Load and instantiate
            except Exception:
                log.error('Error loading kernel provider', exc_info=True)
            else:
                providers.append(provider)

        return cls(providers)

    @asyncio.coroutine
    def find_kernels(self):
        """
        Iterate over available kernel types.
        Yields 2-tuples of (prefixed_name, attributes)
        """
        for provider in self.providers:
            for kernel_name, attributes in provider.find_kernels():
                kernel_type = provider.id + '/' + kernel_name
                yield kernel_type, attributes

    async def launch(self, name, cwd=None, launch_params=None):
        """
        Launch a kernel of a given kernel type using asyncio.
        """
        provider_id, kernel_id = name.split('/', 1)
        for provider in self.providers:
            if provider_id == provider.id:
                return await provider.launch(kernel_id, cwd=cwd, launch_params=launch_params)
        raise KeyError("Invalid provider id '{provider_id}' found in kernel type '{name}'!".
                       format(provider_id=provider_id, name=name))


async def find_kernels_from_entrypoints():
    kf = KernelFinder.from_entrypoints()
    found_kernels = kf.find_kernels()
    for type_id, info in found_kernels:
        print(type_id)


if __name__ == '__main__':
    run_sync(find_kernels_from_entrypoints())
