from abc import ABCMeta, abstractmethod
import entrypoints
import logging
import six

from traitlets.config import Application
try:
    from json import JSONDecodeError
except ImportError:
    # JSONDecodeError is new in Python 3.5, so while we support 3.4:
    JSONDecodeError = ValueError

from .kernelspec import KernelSpecManager, KernelSpec
from .subproc import SubprocessKernelLauncher

log = logging.getLogger(__name__)


class KernelProviderBase(six.with_metaclass(ABCMeta, object)):
    id = None  # Should be a short string identifying the provider class.

    @abstractmethod
    def find_kernels(self):
        """Return an iterator of (kernel_name, kernel_info_dict) tuples."""
        pass

    @abstractmethod
    def launch(self, name, cwd=None, launch_params=None):
        """Launch a kernel, return (connection_info, kernel_manager).

        name will be one of the kernel names produced by find_kernels()

        This method launches and manages the kernel in a blocking manner.
        """
        pass

    def launch_async(self, name, cwd=None, launch_params=None):
        """Launch a kernel asynchronously using asyncio.

        name will be one of the kernel names produced by find_kernels()

        This method should act as an asyncio coroutine, returning an object
        with the AsyncKernelManager interface. This closely matches the
        synchronous KernelManager2 interface, but all methods are coroutines.
        """
        raise NotImplementedError()

    def load_config(self, config=None):
        """Loads the configuration corresponding to the hosting application.  This method
        is called during KernelFinder initialization prior to any other methods.
        Provider is responsible for interpreting the `config` parameter (when present) which will be
        an instance of Config: https://traitlets.readthedocs.io/en/stable/config.html#the-main-concepts
        """
        pass


class KernelSpecProvider(KernelProviderBase):
    """Offers kernel types from installed kernelspec directories.
    """
    id = 'spec'
    kernel_file = 'kernel.json'

    def __init__(self, search_path=None):
        self.ksm = KernelSpecManager(kernel_dirs=search_path, kernel_file=self.kernel_file)

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

    def launch(self, name, cwd=None, launch_params=None):
        spec = self.ksm.get_kernel_spec(name)
        launcher = SubprocessKernelLauncher(kernel_cmd=spec.argv, extra_env=spec.env, cwd=cwd,
                                            launch_params=launch_params)
        return launcher.launch()

    def launch_async(self, name, cwd=None, launch_params=None):
        from .subproc.async_manager import AsyncSubprocessKernelLauncher
        spec = self.ksm.get_kernel_spec(name)
        return AsyncSubprocessKernelLauncher(
            kernel_cmd=spec.argv, extra_env=spec.env, cwd=cwd, launch_params=launch_params).launch()


class IPykernelProvider(KernelProviderBase):
    """Offers a kernel type using the Python interpreter it's running in.

    This checks if ipykernel is importable first.
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

    def find_kernels(self):
        info = self._check_for_kernel()

        if info:
            yield 'kernel', {
                'language_info': info['language_info'],
                'display_name': info['spec']['display_name'],
                'argv': info['spec']['argv'],
                'resource_dir': info['resource_dir'],
            }

    def launch(self, name, cwd=None, launch_params=None):
        info = self._check_for_kernel()
        if info is None:
            raise Exception("ipykernel is not importable")

        launcher = SubprocessKernelLauncher(kernel_cmd=info['spec']['argv'],
                                            extra_env={}, cwd=cwd, launch_params=launch_params)
        return launcher.launch()

    def launch_async(self, name, cwd=None, launch_params=None):
        from .subproc.async_manager import AsyncSubprocessKernelLauncher
        info = self._check_for_kernel()
        if info is None:
            raise Exception("ipykernel is not importable")
        return AsyncSubprocessKernelLauncher(
            kernel_cmd=info['spec']['argv'], extra_env={}, cwd=cwd, launch_params=launch_params).launch()


class KernelFinder(object):
    """Manages a collection of kernel providers to find available kernel types

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
        """Load all kernel providers advertised by entry points.

        Kernel providers should use the "jupyter_client.kernel_providers"
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

    def find_kernels(self):
        """Iterate over available kernel types.

        Yields 2-tuples of (prefixed_name, attributes)
        """
        for provider in self.providers:
            for kernel_name, attributes in provider.find_kernels():
                kernel_type = provider.id + '/' + kernel_name
                yield kernel_type, attributes

    def launch(self, name, cwd=None, launch_params=None):
        """Launch a kernel of a given kernel type.
        """
        provider_id, kernel_id = name.split('/', 1)
        for provider in self.providers:
            if provider_id == provider.id:
                return provider.launch(kernel_id, cwd=cwd, launch_params=launch_params)
        raise KeyError(provider_id)

    def launch_async(self, name, cwd=None, launch_params=None):
        """Launch a kernel of a given kernel type, using asyncio.
        """
        provider_id, kernel_id = name.split('/', 1)
        for provider in self.providers:
            if provider_id == provider.id:
                return provider.launch_async(kernel_id, cwd=cwd, launch_params=launch_params)
        raise KeyError(provider_id)


def main():
    kf = KernelFinder.from_entrypoints()
    for type_id, info in kf.find_kernels():
        print(type_id)


if __name__ == '__main__':
    main()
