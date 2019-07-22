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
import sys
import unittest

import pytest

if str is bytes: # py2
    StringIO = io.BytesIO
else:
    StringIO = io.StringIO

from ipython_genutils.tempdir import TemporaryDirectory
from jupyter_kernel_mgmt import kernelspec
from jupyter_core import paths
from .utils import test_env

sample_kernel_json = {'argv':['cat', '{connection_file}'],
                      'display_name':'Test kernel',
                     }


def install_sample_kernel(kernels_dir, kernel_name='sample', kernel_file='kernel.json'):
    """install a sample kernel in a kernels directory"""
    sample_kernel_dir = pjoin(kernels_dir, kernel_name)
    os.makedirs(sample_kernel_dir)
    json_file = pjoin(sample_kernel_dir, kernel_file)
    with open(json_file, 'w') as f:
        json.dump(sample_kernel_json, f)
    return sample_kernel_dir


class KernelSpecTests(unittest.TestCase):

    def setUp(self):
        self.env_patch = test_env()
        self.env_patch.start()
        self.sample_kernel_dir = install_sample_kernel(
            pjoin(paths.jupyter_data_dir(), 'kernels'))
        self.prov_sample1_kernel_dir = install_sample_kernel(
            pjoin(paths.jupyter_data_dir(), 'kernels'), 'prov_sample1', 'prov_kernel.json')
        self.prov_sample2_kernel_dir = install_sample_kernel(
            pjoin(paths.jupyter_data_dir(), 'kernels'), 'prov_sample2', 'prov_kernel.json')

        self.ksm = kernelspec.KernelSpecManager()
        self.prov_ksm = kernelspec.KernelSpecManager(kernel_file='prov_kernel.json')

        td2 = TemporaryDirectory()
        self.addCleanup(td2.cleanup)
        self.installable_kernel = td2.name
        with open(pjoin(self.installable_kernel, 'kernel.json'), 'w') as f:
            json.dump(sample_kernel_json, f)

    def tearDown(self):
        self.env_patch.stop()

    def test_find_kernel_specs(self):
        kernels = self.ksm.find_kernel_specs()
        self.assertEqual(kernels['sample'], self.sample_kernel_dir)
        self.assertNotIn('prov_sample1', kernels)
        self.assertNotIn('prov_sample2', kernels)

    def test_get_kernel_spec(self):
        ks = self.ksm.get_kernel_spec('SAMPLE')  # Case insensitive
        self.assertEqual(ks.resource_dir, self.sample_kernel_dir)
        self.assertEqual(ks.argv, sample_kernel_json['argv'])
        self.assertEqual(ks.display_name, sample_kernel_json['display_name'])
        self.assertEqual(ks.env, {})
        self.assertEqual(ks.metadata, {})
        with self.assertRaises(kernelspec.NoSuchKernel):
            self.ksm.get_kernel_spec('prov1_sample')

    def test_find_all_specs(self):
        kernels = self.ksm.get_all_specs()
        self.assertEqual(kernels['sample']['resource_dir'], self.sample_kernel_dir)
        self.assertIsNotNone(kernels['sample']['spec'])
    
    def test_kernel_spec_priority(self):
        td = TemporaryDirectory()
        self.addCleanup(td.cleanup)
        sample_kernel = install_sample_kernel(td.name)
        self.ksm.kernel_dirs.append(td.name)
        kernels = self.ksm.find_kernel_specs()
        self.assertEqual(kernels['sample'], self.sample_kernel_dir)
        self.ksm.kernel_dirs.insert(0, td.name)
        kernels = self.ksm.find_kernel_specs()
        self.assertEqual(kernels['sample'], sample_kernel)

    def test_install_kernel_spec(self):
        self.ksm.install_kernel_spec(self.installable_kernel,
                                     kernel_name='tstinstalled',
                                     user=True)
        self.assertIn('tstinstalled', self.ksm.find_kernel_specs())
        
        # install again works
        self.ksm.install_kernel_spec(self.installable_kernel,
                                     kernel_name='tstinstalled',
                                     user=True)

    def test_install_kernel_spec_prefix(self):
        td = TemporaryDirectory()
        self.addCleanup(td.cleanup)
        capture = StringIO()
        handler = StreamHandler(capture)
        self.ksm.log.addHandler(handler)
        self.ksm.install_kernel_spec(self.installable_kernel,
                                     kernel_name='tstinstalled',
                                     prefix=td.name)
        captured = capture.getvalue()
        self.ksm.log.removeHandler(handler)
        self.assertIn("may not be found", captured)
        self.assertNotIn('tstinstalled', self.ksm.find_kernel_specs())

        # add prefix to path, so we find the spec
        self.ksm.kernel_dirs.append(pjoin(td.name, 'share', 'jupyter', 'kernels'))
        self.assertIn('tstinstalled', self.ksm.find_kernel_specs())
    
        # Run it again, no warning this time because we've added it to the path
        capture = StringIO()
        handler = StreamHandler(capture)
        self.ksm.log.addHandler(handler)
        self.ksm.install_kernel_spec(self.installable_kernel,
                                     kernel_name='tstinstalled',
                                     prefix=td.name)
        captured = capture.getvalue()
        self.ksm.log.removeHandler(handler)
        self.assertNotIn("may not be found", captured)

    @pytest.mark.skipif(
        not (os.name != 'nt' and not os.access('/usr/local/share', os.W_OK)),
        reason="needs Unix system without root privileges")
    def test_cant_install_kernel_spec(self):
        with self.assertRaises(OSError):
            self.ksm.install_kernel_spec(self.installable_kernel,
                                         kernel_name='tstinstalled',
                                         user=False)

    def test_remove_kernel_spec(self):
        path = self.ksm.remove_kernel_spec('sample')
        self.assertEqual(path, self.sample_kernel_dir)

    def test_remove_kernel_spec_app(self):
        p = Popen(
            [sys.executable, '-m', 'jupyter_client.kernelspecapp', 'remove', 'sample', '-f'],
            stdout=PIPE, stderr=STDOUT,
            env=os.environ,
        )
        out, _ = p.communicate()
        self.assertEqual(p.returncode, 0, out.decode('utf8', 'replace'))

    def test_validate_kernel_name(self):
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

    def test_provider_find_kernel_specs(self):
        kernels = self.prov_ksm.find_kernel_specs()
        self.assertEqual(kernels['prov_sample2'], self.prov_sample2_kernel_dir)
        self.assertNotIn('sample', kernels)

    def test_provider_get_kernel_spec(self):
        ks = self.prov_ksm.get_kernel_spec('PROV_SAMPLE1')  # Case insensitive
        self.assertEqual(ks.resource_dir, self.prov_sample1_kernel_dir)
        self.assertEqual(ks.argv, sample_kernel_json['argv'])
        self.assertEqual(ks.display_name, sample_kernel_json['display_name'])
        self.assertEqual(ks.env, {})
        self.assertEqual(ks.metadata, {})
        with self.assertRaises(kernelspec.NoSuchKernel):
            self.prov_ksm.get_kernel_spec('sample')

    def test_provider_find_all_specs(self):
        kernels = self.prov_ksm.get_all_specs()
        self.assertEqual(len(kernels), 2)
        self.assertEqual(kernels['prov_sample1']['resource_dir'], self.prov_sample1_kernel_dir)
        self.assertIsNotNone(kernels['prov_sample1']['spec'])
