# coding: utf-8
"""Tests for the KernelSpecManager"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import io
import copy
import json
from logging import StreamHandler
import os
from os.path import join as pjoin
from subprocess import Popen, PIPE, STDOUT
import shutil
import sys

import pytest

if str is bytes: # py2
    StringIO = io.BytesIO
else:
    StringIO = io.StringIO

from ipython_genutils.tempdir import TemporaryDirectory
from jupyter_kernel_mgmt import kernelspec
from jupyter_core import paths
from .utils import install_sample_kernel, setup_env, sample_kernel_json


@pytest.fixture
def setup_test(setup_env):
    pytest.sample_kernel_dir = install_sample_kernel(
        pjoin(paths.jupyter_data_dir(), 'kernels'))
    pytest.prov_sample1_kernel_dir = install_sample_kernel(
        pjoin(paths.jupyter_data_dir(), 'kernels'), 'prov_sample1', 'prov_kernel.json')
    pytest.prov_sample2_kernel_dir = install_sample_kernel(
        pjoin(paths.jupyter_data_dir(), 'kernels'), 'prov_sample2', 'prov_kernel.json')

    pytest.ksm = kernelspec.KernelSpecManager()
    pytest.prov_ksm = kernelspec.KernelSpecManager(kernel_file='prov_kernel.json')

    td2 = TemporaryDirectory()
    pytest.installable_kernel = td2.name
    with open(pjoin(pytest.installable_kernel, 'kernel.json'), 'w') as f:
        json.dump(sample_kernel_json, f)

    yield pytest.installable_kernel
    shutil.rmtree(pytest.installable_kernel)


def test_find_kernel_specs(setup_test):
    kernels = pytest.ksm.find_kernel_specs()
    assert kernels['sample'] == pytest.sample_kernel_dir
    assert 'prov_sample1' not in kernels
    assert 'prov_sample2' not in kernels


def test_get_kernel_spec(setup_test):
    ks = pytest.ksm.get_kernel_spec('SAMPLE')  # Case insensitive
    assert ks.resource_dir == pytest.sample_kernel_dir
    assert ks.argv == sample_kernel_json['argv']
    assert ks.display_name == sample_kernel_json['display_name']
    assert ks.env == {}
    assert ks.metadata == {}
    with pytest.raises(kernelspec.NoSuchKernel):
        pytest.ksm.get_kernel_spec('prov1_sample')


def test_find_all_specs(setup_test):
    kernels = pytest.ksm.get_all_specs()
    assert kernels['sample']['resource_dir'] == pytest.sample_kernel_dir
    assert kernels['sample']['spec'] is not None


def test_kernel_spec_priority(tmpdir, setup_test):
    sample_kernel = install_sample_kernel(tmpdir.dirname)
    pytest.ksm.kernel_dirs.append(tmpdir.dirname)
    kernels = pytest.ksm.find_kernel_specs()
    assert kernels['sample'] == pytest.sample_kernel_dir
    pytest.ksm.kernel_dirs.insert(0, tmpdir.dirname)
    kernels = pytest.ksm.find_kernel_specs()
    assert kernels['sample'] == sample_kernel


def test_install_kernel_spec(setup_test):
    pytest.ksm.install_kernel_spec(pytest.installable_kernel,
                                 kernel_name='tstinstalled',
                                 user=True)
    assert 'tstinstalled' in pytest.ksm.find_kernel_specs()

    # install again works
    pytest.ksm.install_kernel_spec(pytest.installable_kernel,
                                 kernel_name='tstinstalled',
                                 user=True)
    pytest.ksm.remove_kernel_spec('tstinstalled')


def test_install_kernel_spec_prefix(tmpdir, setup_test):
    capture = StringIO()
    handler = StreamHandler(capture)
    pytest.ksm.log.addHandler(handler)
    pytest.ksm.install_kernel_spec(pytest.installable_kernel,
                                 kernel_name='tstinstalled',
                                 prefix=tmpdir.dirname)
    captured = capture.getvalue()
    pytest.ksm.log.removeHandler(handler)
    assert "may not be found" in captured
    assert 'tstinstalled' not in pytest.ksm.find_kernel_specs()

    # add prefix to path, so we find the spec
    pytest.ksm.kernel_dirs.append(pjoin(tmpdir.dirname, 'share', 'jupyter', 'kernels'))
    assert 'tstinstalled' in pytest.ksm.find_kernel_specs()

    # Run it again, no warning this time because we've added it to the path
    capture = StringIO()
    handler = StreamHandler(capture)
    pytest.ksm.log.addHandler(handler)
    pytest.ksm.install_kernel_spec(pytest.installable_kernel,
                                 kernel_name='tstinstalled',
                                 prefix=tmpdir.dirname)
    captured = capture.getvalue()
    pytest.ksm.log.removeHandler(handler)
    assert "may not be found" not in captured
    pytest.ksm.remove_kernel_spec('tstinstalled')

@pytest.mark.skipif(
    not (os.name != 'nt' and not os.access('/usr/local/share', os.W_OK)),
    reason="needs Unix system without root privileges")
def test_cant_install_kernel_spec(setup_test):
    with pytest.raises(OSError):
        pytest.ksm.install_kernel_spec(pytest.installable_kernel,
                                     kernel_name='tstinstalled',
                                     user=False)


def test_remove_kernel_spec(setup_test):
    path = pytest.ksm.remove_kernel_spec('sample')
    assert path == pytest.sample_kernel_dir


def test_remove_kernel_spec_app(setup_test):
    p = Popen(
        [sys.executable, '-m', 'jupyter_client.kernelspecapp', 'remove', 'sample', '-f'],
        stdout=PIPE, stderr=STDOUT,
        env=os.environ,
    )
    out, _ = p.communicate()
    assert p.returncode == 0, out.decode('utf8', 'replace')


def test_validate_kernel_name(setup_test):
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


def test_provider_find_kernel_specs(setup_test):
    kernels = pytest.prov_ksm.find_kernel_specs()
    assert kernels['prov_sample2'] == pytest.prov_sample2_kernel_dir
    assert 'sample' not in kernels


def test_provider_get_kernel_spec(setup_test):
    ks = pytest.prov_ksm.get_kernel_spec('PROV_SAMPLE1')  # Case insensitive
    assert ks.resource_dir == pytest.prov_sample1_kernel_dir
    assert ks.argv == sample_kernel_json['argv']
    assert ks.display_name == sample_kernel_json['display_name']
    assert ks.env == {}
    assert ks.metadata == {}
    with pytest.raises(kernelspec.NoSuchKernel):
        pytest.prov_ksm.get_kernel_spec('sample')


def test_provider_find_all_specs(setup_test):
    kernels = pytest.prov_ksm.get_all_specs()
    assert len(kernels) == 2
    assert kernels['prov_sample1']['resource_dir'] == pytest.prov_sample1_kernel_dir
    assert kernels['prov_sample1']['spec'] is not None
