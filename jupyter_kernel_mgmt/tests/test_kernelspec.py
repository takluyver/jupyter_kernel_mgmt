# coding: utf-8
"""Tests for the KernelSpecManager"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import io
import json
from logging import StreamHandler
import os
from os.path import join as pjoin
from subprocess import Popen, PIPE, STDOUT
import shutil
import sys

import pytest

from ipython_genutils.tempdir import TemporaryDirectory
from jupyter_kernel_mgmt import kernelspec
from jupyter_core import paths
from .utils import install_sample_kernel, sample_kernel_json


@pytest.fixture
def sample_kernel_dir(setup_env):
    kernel_dir = install_sample_kernel(pjoin(paths.jupyter_data_dir(), 'kernels'))
    return kernel_dir


@pytest.fixture
def prov_sample1_kernel_dir(setup_env):
    kernel_dir = install_sample_kernel(
        pjoin(paths.jupyter_data_dir(), 'kernels'), 'prov_sample1', 'prov_kernel.json')
    return kernel_dir


@pytest.fixture
def prov_sample2_kernel_dir(setup_env):
    kernel_dir = install_sample_kernel(
        pjoin(paths.jupyter_data_dir(), 'kernels'), 'prov_sample2', 'prov_kernel.json')
    return kernel_dir


@pytest.fixture
def ksm(setup_env):
    spec_mgr = kernelspec.KernelSpecManager()
    return spec_mgr


@pytest.fixture
def prov_ksm(setup_env):
    spec_mgr = kernelspec.KernelSpecManager(kernel_file='prov_kernel.json')
    return spec_mgr


@pytest.fixture
def installable_kernel(setup_env):
    td2 = TemporaryDirectory()
    kernel_dir = td2.name
    with open(pjoin(kernel_dir, 'kernel.json'), 'w') as f:
        json.dump(sample_kernel_json, f)

    yield kernel_dir
    shutil.rmtree(kernel_dir)


def test_find_kernel_specs(ksm, sample_kernel_dir):
    kernels = ksm.find_kernel_specs()
    assert kernels['sample'] == sample_kernel_dir
    assert 'prov_sample1' not in kernels
    assert 'prov_sample2' not in kernels


def test_get_kernel_spec(ksm, sample_kernel_dir):
    ks = ksm.get_kernel_spec('SAMPLE')  # Case insensitive
    assert ks.resource_dir == sample_kernel_dir
    assert ks.argv == sample_kernel_json['argv']
    assert ks.display_name == sample_kernel_json['display_name']
    assert ks.env == {}
    assert ks.metadata == {}
    with pytest.raises(kernelspec.NoSuchKernel):
        ksm.get_kernel_spec('prov1_sample')


def test_find_all_specs(ksm, sample_kernel_dir):
    kernels = ksm.get_all_specs()
    assert kernels['sample']['resource_dir'] == sample_kernel_dir
    assert kernels['sample']['spec'] is not None


def test_kernel_spec_priority(tmpdir, ksm, sample_kernel_dir):
    sample_kernel = install_sample_kernel(tmpdir.dirname)
    ksm.kernel_dirs.append(tmpdir.dirname)
    kernels = ksm.find_kernel_specs()
    assert kernels['sample'] == sample_kernel_dir
    ksm.kernel_dirs.insert(0, tmpdir.dirname)
    kernels = ksm.find_kernel_specs()
    assert kernels['sample'] == sample_kernel


def test_install_kernel_spec(ksm, installable_kernel):
    ksm.install_kernel_spec(installable_kernel,
                                 kernel_name='tstinstalled',
                                 user=True)
    assert 'tstinstalled' in ksm.find_kernel_specs()

    # install again works
    ksm.install_kernel_spec(installable_kernel,
                            kernel_name='tstinstalled',
                            user=True)
    ksm.remove_kernel_spec('tstinstalled')


def test_install_kernel_spec_prefix(tmpdir, ksm, installable_kernel):
    capture = io.StringIO()
    handler = StreamHandler(capture)
    ksm.log.addHandler(handler)
    ksm.install_kernel_spec(installable_kernel,
                            kernel_name='tstinstalled',
                            prefix=tmpdir.dirname)
    captured = capture.getvalue()
    ksm.log.removeHandler(handler)
    assert "may not be found" in captured
    assert 'tstinstalled' not in ksm.find_kernel_specs()

    # add prefix to path, so we find the spec
    ksm.kernel_dirs.append(pjoin(tmpdir.dirname, 'share', 'jupyter', 'kernels'))
    assert 'tstinstalled' in ksm.find_kernel_specs()

    # Run it again, no warning this time because we've added it to the path
    capture = io.StringIO()
    handler = StreamHandler(capture)
    ksm.log.addHandler(handler)
    ksm.install_kernel_spec(installable_kernel,
                            kernel_name='tstinstalled',
                            prefix=tmpdir.dirname)
    captured = capture.getvalue()
    ksm.log.removeHandler(handler)
    assert "may not be found" not in captured
    ksm.remove_kernel_spec('tstinstalled')

@pytest.mark.skipif(
    (os.name == 'nt' or os.access('/usr/local/share', os.W_OK)),
    reason="needs Unix system without root privileges")
def test_cant_install_kernel_spec(ksm, installable_kernel):
    with pytest.raises(OSError):
        ksm.install_kernel_spec(installable_kernel,
                                kernel_name='tstinstalled',
                                user=False)


def test_remove_kernel_spec(ksm, sample_kernel_dir):
    path = ksm.remove_kernel_spec('sample')
    assert path == sample_kernel_dir


def test_remove_kernel_spec_app(sample_kernel_dir):
    p = Popen(
        [sys.executable, '-m', 'jupyter_client.kernelspecapp', 'remove', 'sample', '-f'],
        stdout=PIPE, stderr=STDOUT,
        env=os.environ,
    )
    out, _ = p.communicate()
    assert p.returncode == 0, out.decode('utf8', 'replace')


def test_validate_kernel_name(setup_env):
    for good in [
        'julia-0.4',
        'ipython',
        'R',
        'python_3',
        'Haskell-1-2-3',
    ]:
        assert kernelspec._is_valid_kernel_name(good)

    for bad in [
        'has space',
        u'ünicode',
        '%percent',
        'question?',
    ]:
        assert not kernelspec._is_valid_kernel_name(bad)


def test_provider_find_kernel_specs(prov_ksm, prov_sample2_kernel_dir):
    kernels = prov_ksm.find_kernel_specs()
    assert kernels['prov_sample2'] == prov_sample2_kernel_dir
    assert 'sample' not in kernels


def test_provider_get_kernel_spec(prov_ksm, prov_sample1_kernel_dir):
    ks = prov_ksm.get_kernel_spec('PROV_SAMPLE1')  # Case insensitive
    assert ks.resource_dir == prov_sample1_kernel_dir
    assert ks.argv == sample_kernel_json['argv']
    assert ks.display_name == sample_kernel_json['display_name']
    assert ks.env == {}
    assert ks.metadata == {}
    with pytest.raises(kernelspec.NoSuchKernel):
        prov_ksm.get_kernel_spec('sample')


def test_provider_find_all_specs(prov_ksm, prov_sample1_kernel_dir):
    kernels = prov_ksm.get_all_specs()
    assert len(kernels) == 2
    assert kernels['prov_sample1']['resource_dir'] == prov_sample1_kernel_dir
    assert kernels['prov_sample1']['spec'] is not None
