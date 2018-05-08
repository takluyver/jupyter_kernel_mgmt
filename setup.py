#!/usr/bin/env python
# coding: utf-8

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from __future__ import print_function

# the name of the project
name = 'jupyter_kernel_mgmt'

import os
import sys
from setuptools import setup
from setuptools.command.bdist_egg import bdist_egg

v = sys.version_info
if v[:2] < (3, 4):
    error = "ERROR: %s requires Python version 3.4 or above." % name
    print(error, file=sys.stderr)
    sys.exit(1)

pjoin = os.path.join
here = os.path.abspath(os.path.dirname(__file__))
pkg_root = pjoin(here, name)

packages = []
for d, _, _ in os.walk(pjoin(here, name)):
    if os.path.exists(pjoin(d, '__init__.py')):
        packages.append(d[len(here)+1:].replace(os.path.sep, '.'))

version_ns = {}
with open(pjoin(here, name, '_version.py')) as f:
    exec(f.read(), {}, version_ns)

class bdist_egg_disabled(bdist_egg):
    """Disabled version of bdist_egg

    Prevents setup.py install from performing setuptools' default easy_install,
    which it should never ever do.
    """
    def run(self):
        sys.exit("Aborting implicit building of eggs. Use `pip install .` to install from source.")


setup_args = dict(
    name            = name,
    version         = version_ns['__version__'],
    packages        = packages,
    description     = "Jupyter protocol implementation and client libraries",
    author          = 'Jupyter Development Team',
    author_email    = 'jupyter@googlegroups.com',
    url             = 'https://jupyter.org',
    license         = 'BSD',
    classifiers     = [
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
    install_requires = [
        'traitlets',
        'jupyter_core',
        'jupyter_protocol',
        'pyzmq>=13',
        'python-dateutil>=2.1',
        'entrypoints',
    ],
    extras_require   = {
        'test': ['ipykernel', 'ipython', 'mock', 'pytest'],
    },
    python_requires = ">=3.4",
    cmdclass         = {
        'bdist_egg': bdist_egg if 'bdist_egg' in sys.argv else bdist_egg_disabled,
    },
    entry_points     = {
        'console_scripts': [
            # 'jupyter-kernelspec = jupyter_kernel_mgmt.kernelspecapp:KernelSpecApp.launch_instance',
            # 'jupyter-run = jupyter_kernel_mgmt.runapp:RunApp.launch_instance',
            # 'jupyter-kernel = jupyter_kernel_mgmt.kernelapp:main',
        ],
        'jupyter_kernel_mgmt.kernel_type_providers' : [
            'spec = jupyter_kernel_mgmt.discovery:KernelSpecProvider',
            'pyimport = jupyter_kernel_mgmt.discovery:IPykernelProvider',
        ]
    },
)


if __name__ == '__main__':
    setup(**setup_args)
