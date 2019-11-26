"""Tests for Kernel Management Discovery"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import asyncio
import logging
import os
import pytest
import sys

from os.path import join as pjoin
from subprocess import Popen, PIPE, STDOUT

from jupyter_kernel_mgmt import discovery, kernelspec
from jupyter_kernel_mgmt.managerabc import KernelManagerABC
from jupyter_kernel_mgmt.subproc.manager import KernelManager
from jupyter_core import paths
from .utils import install_sample_kernel
from traitlets import List, Unicode
from traitlets.config import Application, SingletonConfigurable


class DummyKernelProvider(discovery.KernelProviderBase):
    """A dummy kernel provider for testing KernelFinder"""
    id = 'dummy'

    @asyncio.coroutine
    def find_kernels(self):
        yield 'sample', {'argv': ['dummy_kernel']}

    async def launch(self, name, cwd=None, launch_params=None):
        return {}, DummyKernelManager()


class DummyKernelSpecProvider(discovery.KernelSpecProvider):
    """A dummy kernelspec provider subclass for testing KernelFinder and KernelSpecProvider subclasses"""
    id = 'dummy_kspec'
    kernel_file = 'dummy_kspec.json'

    # find_kernels() is inherited from KernelsSpecProvider

    async def launch(self, name, cwd=None, launch_params=None):
        return {}, DummyKernelManager()


class LaunchParamsKernelProvider(discovery.KernelSpecProvider):
    """A dummy kernelspec provider subclass for testing KernelFinder and KernelSpecProvider subclasses"""
    id = 'params_kspec'
    kernel_file = 'params_kspec.json'

    # find_kernels() and launch() are inherited from KernelsSpecProvider


class DummyKernelManager(KernelManagerABC):
    _alive = True

    async def is_alive(self):
        """Check whether the kernel is currently alive (e.g. the process exists)
        """
        return self._alive

    async def wait(self, timeout):
        """Wait for the kernel process to exit.
        """
        return False

    async def signal(self, signum):
        """Send a signal to the kernel."""
        pass

    async def interrupt(self):
        pass

    async def kill(self):
        self._alive = False


class ProviderApplication(Application):
    name = 'ProviderApplication'
    my_app = Unicode('my_app', config=True,)


class ProviderConfig(SingletonConfigurable):
    my_argv = List(Unicode(), ['default_argv'], config=True,)
    my_foo = Unicode('foo.bar', config=True,)


class TestConfigKernelProvider(DummyKernelProvider):
    """A dummy kernel provider for testing KernelFinder with configuration loading"""
    id = 'config'

    config = None
    argv = ['dummy_config_kernel']  # will be replace by config item

    @asyncio.coroutine
    def find_kernels(self):
        argv = self.argv
        if self.config:
            argv = self.config.my_argv
            assert self.config.my_foo == 'foo.bar'  # verify default config value

        yield 'sample', {'argv': argv}

    def load_config(self, config=None):
        self.config = ProviderConfig.instance(config=config)


# Use the asyncio mark for all tests
pytestmark = pytest.mark.asyncio


@pytest.fixture
def setup_test(setup_env):
    install_sample_kernel(pjoin(paths.jupyter_data_dir(), 'kernels'))
    install_sample_kernel(pjoin(paths.jupyter_data_dir(), 'kernels'), 'dummy_kspec1', 'dummy_kspec.json')
    install_sample_kernel(pjoin(paths.jupyter_data_dir(), 'kernels'), 'dummy_kspec2', 'dummy_kspec.json')

    # This provides an example of what a kernel provider might do for describing the launch parameters
    # it supports.  By creating the metadata in the form of JSON schema, applications can easily build
    # forms that gather the values.
    # Note that not all parameters are fed to `argv`.  Some may be used by the provider
    # to configure an environment (e.g., a kubernetes pod) in which the kernel will run.  The idea
    # is that the front-end will get the parameter metadata, consume and prompt for values, and return
    # the launch_parameters (name, value pairs) in the kernel startup POST json body, which then
    # gets passed into the kernel provider's launch method.
    #
    # See test_kernel_launch_params() for usage.

    params_json = {'argv': ['tail', '{follow}', '-n {line_count}', '{connection_file}'],
                   'display_name': 'Test kernel',
                   'metadata': {
                       'launch_parameter_schema': {
                           "title": "Params_kspec Kernel Provider Launch Parameter Schema",
                           "properties": {
                               "line_count": {"type": "integer", "minimum": 1, "default": 20,
                                              "description": "The number of lines to tail"},
                               "follow": {"type": "string", "enum": ["-f", "-F"], "default": "-f",
                                          "description": "The follow option to tail"},
                               "cpus": {"type": "number", "minimum": 0.5, "maximum": 8.0, "default": 4.0,
                                        "description": "The number of CPUs to use for this kernel"},
                               "memory": {"type": "integer", "minimum": 2, "maximum": 1024, "default": 8,
                                          "description": "The number of GB to reserve for memory for this kernel"}
                           },
                           "required": ["line_count", "follow"]
                       }
                   }
                   }
    install_sample_kernel(pjoin(paths.jupyter_data_dir(), 'kernels'), 'params_kspec', 'params_kspec.json',
                          kernel_json=params_json)


async def test_ipykernel_provider(setup_test):
    import ipykernel  # Fail clearly if ipykernel not installed
    ikf = discovery.IPykernelProvider()

    res = list(ikf.find_kernels())
    assert len(res) == 1, res
    name, info = res[0]
    assert name == 'kernel'
    assert info['argv'][0] == sys.executable


async def test_meta_kernel_finder(setup_test):
    kf = discovery.KernelFinder(providers=[DummyKernelProvider()])
    assert list(kf.find_kernels()) == \
        [('dummy/sample', {'argv': ['dummy_kernel']})]

    conn_info, manager = await kf.launch('dummy/sample')
    assert isinstance(manager, DummyKernelManager)


async def test_kernel_spec_provider(setup_test):
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

    with pytest.raises(kernelspec.NoSuchKernel):
        await kf.launch('spec/dummy_kspec1')

    conn_info, manager = await kf.launch('spec/sample')
    assert isinstance(manager, KernelManager)
    # this actually starts a kernel, so let's make sure its terminated
    await manager.kill()


async def test_kernel_spec_provider_subclass(setup_test):
    kf = discovery.KernelFinder(providers=[DummyKernelSpecProvider()])

    dummy_kspecs = list(kf.find_kernels())
    assert len(dummy_kspecs) == 2

    for name, spec in dummy_kspecs:
        assert name.startswith('dummy_kspec/dummy_kspec')
        assert spec['argv'] == ['cat', '{connection_file}']

    conn_info, manager = await kf.launch('dummy_kspec/dummy_kspec1')
    assert isinstance(manager, DummyKernelManager)
    await manager.kill()  # no process was started, so this is only for completeness


async def test_kernel_launch_params(caplog, setup_test):
    kf = discovery.KernelFinder(providers=[LaunchParamsKernelProvider()])

    kspecs = list(kf.find_kernels())

    count = 0
    param_spec = None
    for name, spec in kspecs:
        if name == 'params_kspec/params_kspec':
            param_spec = spec
            count += 1

    assert count == 1
    assert param_spec['argv'] == ['tail', '{follow}', '-n {line_count}', '{connection_file}']

    # application gathers launch parameters here... Since this is full schema, application will likely
    # just access: param_spec['metadata']['launch_parameter_schema']
    #
    line_count_schema = param_spec['metadata']['launch_parameter_schema']['properties']['line_count']
    follow_schema = param_spec['metadata']['launch_parameter_schema']['properties']['follow']
    cpus_schema = param_spec['metadata']['launch_parameter_schema']['properties']['cpus']
    memory_schema = param_spec['metadata']['launch_parameter_schema']['properties']['memory']

    # validate we have our metadata
    assert line_count_schema['minimum'] == 1
    assert follow_schema['default'] == '-f'
    assert cpus_schema['maximum'] == 8.0
    assert memory_schema['description'] == "The number of GB to reserve for memory for this kernel"

    # Kernel provider would be responsible for validating values against the schema upon return from client.
    # This includes setting any default values for parameters that were not included, etc.  The following
    # simulates the parameter gathering...
    launch_params = dict()
    launch_params['follow'] = follow_schema['enum'][0]
    launch_params['line_count'] = 8
    launch_params['cpus'] = cpus_schema['default']
    # add a "system-owned" parameter - connection_file - ensure this value is NOT substituted.
    launch_params['connection_file'] = 'bad_param'

    # capture DEBUG output in order to confirm argv substitutions
    with caplog.at_level(logging.DEBUG):
        conn_info, manager = await kf.launch('params_kspec/params_kspec', launch_params=launch_params)
        assert isinstance(manager, KernelManager)
        assert "Starting kernel cmd: ['tail', '-f', '-n 8'," in caplog.text

        # this actually starts a tail -f command, so let's make sure its terminated
        await manager.kill()


async def test_load_config(setup_test):
    # create fake application
    app = ProviderApplication()
    app.launch_instance(argv=["--ProviderConfig.my_argv=['xxx','yyy']"])

    kf = discovery.KernelFinder(providers=[TestConfigKernelProvider()])
    dummy_kspecs = list(kf.find_kernels())

    count = 0
    found_argv = []
    for name, spec in dummy_kspecs:
        if name == 'config/sample':
            found_argv = spec['argv']
            count += 1

    assert count == 1
    assert found_argv == ['xxx', 'yyy']


async def test_discovery_main(setup_test):
    p = Popen(
        [sys.executable, '-m', 'jupyter_kernel_mgmt.discovery'],
        stdout=PIPE, stderr=STDOUT,
        #env=os.environ,
    )
    out, err = p.communicate()
    assert err is None
    assert b'spec/sample' in out
