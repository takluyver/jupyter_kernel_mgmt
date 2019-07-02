"""Tools for managing kernel specs"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import io
import json
import os
import re
import shutil
import warnings

pjoin = os.path.join

from traitlets import (
    HasTraits, List, Unicode, Dict, CaselessStrEnum
)

from traitlets.log import get_logger as get_app_logger

from jupyter_core.paths import jupyter_data_dir, jupyter_path, SYSTEM_JUPYTER_PATH


DEFAULT_KERNEL_FILE = 'kernel.json'


class KernelSpec(HasTraits):
    argv = List()
    display_name = Unicode()
    language = Unicode()
    env = Dict()
    resource_dir = Unicode()
    interrupt_mode = CaselessStrEnum(
        ['message', 'signal'], default_value='signal'
    )
    metadata = Dict()

    @classmethod
    def from_resource_dir(cls, resource_dir, kernel_file=DEFAULT_KERNEL_FILE):
        """Create a KernelSpec object by reading spec_file_name (kernel.json)

        Pass the path to the *directory* containing spec_file_name (kernel.json).
        If the file name is something other than kernel.json, it should be passed as well.
        """
        kernel_file = pjoin(resource_dir, kernel_file)
        with io.open(kernel_file, 'r', encoding='utf-8') as f:
            kernel_dict = json.load(f)
        return cls(resource_dir=resource_dir, **kernel_dict)

    def to_dict(self):
        d = dict(argv=self.argv,
                 env=self.env,
                 display_name=self.display_name,
                 language=self.language,
                 interrupt_mode=self.interrupt_mode,
                 metadata=self.metadata,)
        return d

    def to_json(self):
        """Serialise this kernelspec to a JSON object.

        Returns a string.
        """
        return json.dumps(self.to_dict())


_kernel_name_pat = re.compile(r'^[a-z0-9._\-]+$', re.IGNORECASE)


def _is_valid_kernel_name(name):
    """Check that a kernel name is valid."""
    # quote is not unicode-safe on Python 2
    return _kernel_name_pat.match(name)


_kernel_name_description = "Kernel names can only contain ASCII letters and numbers and these separators:" \
 " - . _ (hyphen, period, and underscore)."


class NoSuchKernel(KeyError):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return "No such kernel named {}".format(self.name)


class KernelSpecManager:
    def __init__(self, user_kernel_dir=None, kernel_dirs=None, kernel_file=DEFAULT_KERNEL_FILE):
        super().__init__()
        self.user_kernel_dir = user_kernel_dir or self._user_kernel_dir_default()
        if kernel_dirs is None:
            kernel_dirs = self._kernel_dirs_default()
        self.kernel_dirs = kernel_dirs
        self.kernel_file = kernel_file
        self.log = get_app_logger()

    @staticmethod
    def _user_kernel_dir_default():
        return pjoin(jupyter_data_dir(), 'kernels')

    @staticmethod
    def _kernel_dirs_default():
        dirs = jupyter_path('kernels')
        # At some point, we should stop adding .ipython/kernels to the path,
        # but the cost to keeping it is very small.
        try:
            from IPython.paths import get_ipython_dir
        except ImportError:
            try:
                from IPython.utils.path import get_ipython_dir
            except ImportError:
                # no IPython, no ipython dir
                get_ipython_dir = None
        if get_ipython_dir is not None:
            dirs.append(os.path.join(get_ipython_dir(), 'kernels'))
        return dirs

    def find_kernel_specs(self):
        """Returns a dict mapping kernel names to resource directories."""
        d = {}
        for kernel_dir in self.kernel_dirs:
            kernels = self._list_kernels_in(kernel_dir)
            for kname, spec in kernels.items():
                if kname not in d:
                    self.log.debug("Found kernel %s in %s", kname, kernel_dir)
                    d[kname] = spec

        return d
        # TODO: Caching?

    def get_kernel_spec(self, kernel_name):
        """Returns a :class:`KernelSpec` instance for the given kernel_name.

        Raises :exc:`NoSuchKernel` if the given kernel name is not found.
        """
        d = self.find_kernel_specs()
        try:
            resource_dir = d[kernel_name.lower()]
        except KeyError:
            raise NoSuchKernel(kernel_name)

        return KernelSpec.from_resource_dir(resource_dir, kernel_file=self.kernel_file)

    def get_all_specs(self):
        """Returns a dict mapping kernel names to kernelspecs.

        Returns a dict of the form::

            {
              'kernel_name': {
                'resource_dir': '/path/to/kernel_name',
                'spec': {"the spec itself": ...}
              },
              ...
            }
        """
        d = self.find_kernel_specs()
        return {kname: {
                "resource_dir": d[kname],
                "spec": KernelSpec.from_resource_dir(d[kname], kernel_file=self.kernel_file).to_dict()
                } for kname in d}

    def remove_kernel_spec(self, name):
        """Remove a kernel spec directory by name.

        Returns the path that was deleted.
        """
        specs = self.find_kernel_specs()
        spec_dir = specs[name]
        self.log.debug("Removing %s", spec_dir)
        if os.path.islink(spec_dir):
            os.remove(spec_dir)
        else:
            shutil.rmtree(spec_dir)
        return spec_dir

    def _is_kernel_dir(self, path):
        """Is ``path`` a kernel directory?"""
        return os.path.isdir(path) and os.path.isfile(pjoin(path, self.kernel_file))

    def _list_kernels_in(self, parent_dir):
        """Return a mapping of kernel names to resource directories from dir.

        If dir is None or does not exist, returns an empty dict.
        """
        if parent_dir is None or not os.path.isdir(parent_dir):
            return {}
        kernels = {}
        for f in os.listdir(parent_dir):
            path = pjoin(parent_dir, f)
            if not self._is_kernel_dir(path):
                continue
            key = f.lower()
            if not _is_valid_kernel_name(key):
                warnings.warn("Invalid kernelspec directory name (%s): %s"
                              % (_kernel_name_description, path), stacklevel=3,
                              )
            kernels[key] = path
        return kernels

    def _get_destination_dir(self, kernel_name, user=False, prefix=None):
        if user:
            return os.path.join(self.user_kernel_dir, kernel_name)
        elif prefix:
            return os.path.join(os.path.abspath(prefix), 'share', 'jupyter', 'kernels', kernel_name)
        else:
            return os.path.join(SYSTEM_JUPYTER_PATH[0], 'kernels', kernel_name)

    def install_kernel_spec(self, source_dir, kernel_name=None, user=False,
                            replace=None, prefix=None):
        """Install a kernel spec by copying its directory.

        If ``kernel_name`` is not given, the basename of ``source_dir`` will
        be used.

        If ``user`` is False, it will attempt to install into the systemwide
        kernel registry. If the process does not have appropriate permissions,
        an :exc:`OSError` will be raised.

        If ``prefix`` is given, the kernelspec will be installed to
        PREFIX/share/jupyter/kernels/KERNEL_NAME. This can be sys.prefix
        for installation inside virtual or conda envs.
        """
        source_dir = source_dir.rstrip('/\\')
        if not kernel_name:
            kernel_name = os.path.basename(source_dir)
        kernel_name = kernel_name.lower()
        if not _is_valid_kernel_name(kernel_name):
            raise ValueError("Invalid kernel name %r.  %s" % (kernel_name, _kernel_name_description))

        if user and prefix:
            raise ValueError("Can't specify both user and prefix. Please choose one or the other.")

        if replace is not None:
            warnings.warn(
                "replace is ignored. Installing a kernelspec always replaces an existing installation",
                DeprecationWarning,
                stacklevel=2,
            )

        destination = self._get_destination_dir(kernel_name, user=user, prefix=prefix)
        self.log.debug('Installing kernelspec in %s', destination)

        kernel_dir = os.path.dirname(destination)
        if kernel_dir not in self.kernel_dirs:
            self.log.warning("Installing to %s, which is not in %s. The kernelspec may not be found.",
                        kernel_dir, self.kernel_dirs,
            )

        if os.path.isdir(destination):
            self.log.info('Removing existing kernelspec in %s', destination)
            shutil.rmtree(destination)

        shutil.copytree(source_dir, destination)
        self.log.info('Installed kernelspec %s in %s', kernel_name, destination)
        return destination


def find_kernel_specs(kernel_file=DEFAULT_KERNEL_FILE):
    """Returns a dict mapping kernel names to resource directories."""
    return KernelSpecManager(kernel_file=kernel_file).find_kernel_specs()


def get_kernel_spec(kernel_name, kernel_file=DEFAULT_KERNEL_FILE):
    """Returns a :class:`KernelSpec` instance for the given kernel_name.

    Raises KeyError if the given kernel name is not found.
    """
    return KernelSpecManager(kernel_file=kernel_file).get_kernel_spec(kernel_name)


def install_kernel_spec(source_dir, kernel_name=None, user=False, replace=False, prefix=None):
    return KernelSpecManager().install_kernel_spec(source_dir, kernel_name, user, replace, prefix)


install_kernel_spec.__doc__ = KernelSpecManager.install_kernel_spec.__doc__
