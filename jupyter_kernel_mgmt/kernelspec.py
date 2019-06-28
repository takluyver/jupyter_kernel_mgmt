"""Tools for managing kernel specs"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import io
import json
import logging
import os
import re
import shutil
import warnings

from jupyter_core.paths import jupyter_data_dir, jupyter_path, SYSTEM_JUPYTER_PATH
from tornado import ioloop
from traitlets import (
    HasTraits, List, Unicode, Dict, CaselessStrEnum
)

try:
    from json import JSONDecodeError
except ImportError:
    # JSONDecodeError is new in Python 3.5, so while we support 3.4:
    JSONDecodeError = ValueError

pjoin = os.path.join

# TODO - figure out how to better configure the logging and refresh timeout values...
refresh_timeout = int(os.getenv("KERNELSPEC_CACHE_REFRESH_SECS", "30"))

log_level = os.getenv("KERNELSPEC_LOG_LEVEL", "DEBUG")

logging.basicConfig(format='[%(levelname)1.1s %(asctime)s %(name)s] %(message)s')
log = logging.getLogger(__name__)
log.setLevel(log_level)


DEFAULT_SPEC_PROVIDER = 'spec'


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
    def from_resource_dir(cls, resource_dir):
        """Create a KernelSpec object by reading kernel.json

        Pass the path to the *directory* containing kernel.json.
        """
        kernel_file = pjoin(resource_dir, 'kernel.json')
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


class KernelSpecCacheEntry:
    """A class representing the cache entry of a kernel spec.

       Entries are stored in a dictionary corresponding to each kernel spec provider.  In
       addition to the resource directory and kernel.json (dict), the kernel.json's last
       modification time is also kept.  This value is used to determine stale entries.
       Since entries are also maintained in a flattened set indexed by resource_dir, the
       provider id is also retained as a field.

       Note: files other than kernel.json are not cached.  This can change should we
       decide to store kernel specs in a non-filesystem data store, for example.
    """
    def __init__(self, name, provider_id, last_mod_time, resource_dir, kernel_dict):
        self.name = name
        self.provider_id = provider_id
        self.last_mod_time = last_mod_time
        self.spec = KernelSpec(resource_dir=resource_dir, **kernel_dict)

    def is_stale(self, current_mod_time):
        """ Returns True if this cache entry is considered stale. """
        return current_mod_time > self.last_mod_time


class KernelSpecCache:
    """A singleton class used to cache kernel specs across multiple providers.

       The cache is implemented as two dictionaries - one indexed by kernel spec provider
       id, the other a flattend dict, indexed by path (or resource dir).

       Each provider-based dictionary contains a dictionary of cache entries indexed by
       kernel name.

       The path-based dictionary contains straight cache entries - the same instances
       contained in the provider-based name dictionaries.

       This cache is used to reduce the number of file opens necessary to maintain the
       existence of multiple KernelSpecProvider classes since the distinguishing characteristic
       is a provider id embedded in the kernel.json (with no embedded provider id representing
       the standard kernel spec).

       A periodic callback is used to maintain the cache's consistency with the filesystem.
       This refresh only reloads entries if the last modification time of the kernel.json file
       is more recent than when cached.  The refresh also detects missing kernel directories
       and updates the cache accordingly.

       The cache is self-maintained - no entries are added or removed by callers.
    """

    __inst = None

    @staticmethod
    def get_instance():
        if KernelSpecCache.__inst is None:
            KernelSpecCache()
        return KernelSpecCache.__inst

    def __init__(self):
        if KernelSpecCache.__inst is not None:
            raise RuntimeError("KernelSpecCache is a singleton, use KernelSpecCache.getInstance().")
        KernelSpecCache.__inst = self
        self._entries_by_path = dict()
        self._entries_by_provider = dict()
        self._kernel_dirs = jupyter_path('kernels')
        self._refresh()  # Ensure we're initialized before beginning callback
        self._callback = ioloop.PeriodicCallback(self._refresh, 1000 * refresh_timeout)
        self._callback.start()

    def get_spec(self, provider_id, name):
        """ Returns the KernelSpec corresponding to the given provider and kernel spec name.
            Raises NoSuchKernel is no entry is found or the corresponding resource_dir does't exist.
        """
        entry = self._get_entry(provider_id, name)
        if entry is None:
            raise NoSuchKernel(name)
        # let's also ensure the resource dir is still present since this may not
        # get detected between cache refreshes should the spec have been deleted.
        if not os.path.exists(entry.spec.resource_dir):
            raise NoSuchKernel(name)
        return entry.spec

    def get_specs(self, provider_id):
        """ Returns a dict mapping kernel names to specs for the given provider. """
        d = {}
        entries = self._get_entries(provider_id)
        for name, cache_entry in entries.items():
            # let's also ensure the resource dir is still present since this may not
            # get detected between cache refreshes should the spec have been deleted.
            if os.path.exists(cache_entry.spec.resource_dir):
                d[name] = cache_entry.spec
                log.debug("Found kernel %s in %s", name, cache_entry.spec.resource_dir)
        return d

    def get_resource_dirs(self, provider_id):
        """Returns a dict mapping kernel names to resource directories for the given provider."""
        d = {}
        entries = self._get_entries(provider_id)
        for name, cache_entry in entries.items():
            # let's also ensure the resource dir is still present since this may not
            # get detected between cache refreshes should the spec have been deleted.
            if os.path.exists(cache_entry.spec.resource_dir):
                d[name] = cache_entry.spec.resource_dir
                log.debug("Found kernel %s in %s", name, d[name])
        return d

    def _get_entries(self, provider_id):
        """ Returns all KernelSpecCacheEntries for a given provider or an empty dict. """
        provider_cache = self._entries_by_provider.get(provider_id)
        if provider_cache is not None:
            return provider_cache
        return {}

    def _get_entry(self, provider_id, name):
        """ Returns the KernelSpecCacheEntry for the given provider and kernel spec name or None."""
        provider_cache = self._entries_by_provider.get(provider_id)
        if provider_cache is not None:
            return provider_cache.get(name)
        return None

    def _get_entry_by_path(self, path):
        """ Returns the KernelSpecCacheEntry corresponding to the given path or None. """
        entry = self._entries_by_path.get(path)
        return entry

    def _put_entry(self, entry):
        """ Adds the given KernelSpecCacheEntry. """
        if entry is None:
            return
        provider_cache = self._entries_by_provider.get(entry.provider_id)
        if provider_cache is None:
            provider_cache = dict()
            self._entries_by_provider[entry.provider_id] = provider_cache
        provider_cache[entry.name] = entry
        self._entries_by_path[entry.spec.resource_dir] = entry
        log.debug("KernelSpecCache.put_entry: provider: '{provider}', name: '{name}'".
                  format(provider=entry.provider_id, name=entry.name))

    def _remove_entry_by_path(self, path):
        """ Removes the entry corresponding to path.  This will also update the provider-specific
            set as well.
        """
        entry = self._entries_by_path.pop(path)
        if entry:
            provider_cache = self._entries_by_provider.get(entry.provider_id)
            provider_entry = provider_cache.get(entry.name)
            if provider_cache:
                if provider_entry.spec.resource_dir == entry.spec.resource_dir:
                    provider_cache.pop(entry.name)
                    log.debug("KernelSpecCache._remove_entry_by_path: provider: '{provider}', path: '{path}'".
                          format(provider=entry.provider_id, path=path))
                else:  # kernelspec is considered moved since entry exists by name at a different resource_dir
                    log.debug("KernelSpecCache._remove_entry_by_path: provider: '{provider}', entry: '{name}' has moved"
                              "from: '{old_path}' to: '{new_path}'".
                              format(provider=entry.provider_id, name=entry.name,
                                     old_path=path, new_path=provider_entry.spec.resource_dir))
        else:
            log.debug("KernelSpecCache._remove_entry_by_path: Not found for path: '{path}'".
                      format(path=path))

    def _refresh(self):
        """ Refreshes the cache looking for stale entries as well as entries that no longer exist,
            which are then removed from the cache.

            Note: All updates to the cache occur via this method!
        """
        log.debug("Refreshing kernel spec cache...")

        # First, a list of existing resource dirs is built from existing entries.
        # As each is encountered, the list is pruned.  Should any remain after the
        # set of directories has been exhausted, those represent removed kernelspecs
        # so those entries are then removed from the cache.

        existing_dirs = list(self._entries_by_path.keys())
        for kernel_dir in self._kernel_dirs:
            kernels = _list_kernels_in(kernel_dir)
            for kname, resource_dir in kernels.items():
                self._update_cache(kname, resource_dir)
                if resource_dir in existing_dirs:
                    existing_dirs.remove(resource_dir)

        for path in existing_dirs:  # Remove any cache entries that are no longer found in the file system
            self._remove_entry_by_path(path)

    def _update_cache(self, name, resource_dir):
        """ Performs (possible) caching of kernel.json file located in resource_dir.

            To minimize file opens, it first stats the file for last modification time and checks
            the cache if a) there's an entry for this path and b) if the kernel.json file has not
            been modified since cached.  If both are true, nothing happens.

            If either check was false, the kernel.json file is loaded, checked for a provider_id
            entry, then cached.
        """
        kernel_file = pjoin(resource_dir, 'kernel.json')
        try:
            last_mod_time = os.path.getmtime(kernel_file)

            # If we have a cache entry and its not stale - return, else, open file and
            # add to cache - irrespective of provider.
            cache_entry = self._get_entry_by_path(resource_dir)
            if cache_entry is not None and not cache_entry.is_stale(last_mod_time):
                return

            with io.open(kernel_file, 'r', encoding='utf-8') as f:
                kernel_dict = json.load(f)
        except OSError as ose:
            log.warning("Failed to stat/open kernelspec in %s. Error was: %s", resource_dir, ose)
            return None
        except JSONDecodeError:
            log.warning("Failed to parse kernelspec in %s" % resource_dir)
            return None

        # Determine provider id.  If none is found, the default provider is assumed.
        provider_id = DEFAULT_SPEC_PROVIDER
        if 'metadata' in kernel_dict and 'provider_id' in kernel_dict['metadata']:
            provider_id = kernel_dict['metadata']['provider_id']

        cache_entry = KernelSpecCacheEntry(name, provider_id, last_mod_time, resource_dir, kernel_dict)
        self._put_entry(cache_entry)


_kernel_name_pat = re.compile(r'^[a-z0-9._\-]+$', re.IGNORECASE)


def _is_valid_kernel_name(name):
    """Check that a kernel name is valid."""
    # quote is not unicode-safe on Python 2
    return _kernel_name_pat.match(name)


_kernel_name_description = "Kernel names can only contain ASCII letters and numbers and these separators:" \
 " - . _ (hyphen, period, and underscore)."


def _is_kernel_dir(path):
    """Is ``path`` a kernel directory?"""
    return os.path.isdir(path) and os.path.isfile(pjoin(path, 'kernel.json'))


def _list_kernels_in(parent_dir):
    """Return a mapping of kernel names to resource directories from dir.

    If dir is None or does not exist, returns an empty dict.
    """
    if parent_dir is None or not os.path.isdir(parent_dir):
        return {}
    kernels = {}
    for f in os.listdir(parent_dir):
        path = pjoin(parent_dir, f)
        if not _is_kernel_dir(path):
            continue
        key = f.lower()
        if not _is_valid_kernel_name(key):
            warnings.warn("Invalid kernelspec directory name (%s): %s"
                          % (_kernel_name_description, path), stacklevel=3,)
        kernels[key] = path
    return kernels


class NoSuchKernel(KeyError):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return "No such kernel named {}".format(self.name)


class KernelSpecManager:

    def __init__(self, user_kernel_dir=None, kernel_dirs=None):
        super().__init__()
        self.user_kernel_dir = user_kernel_dir or self._user_kernel_dir_default()
        if kernel_dirs is None:
            kernel_dirs = self._kernel_dirs_default()
        self.kernel_dirs = kernel_dirs
        self.cache = KernelSpecCache.get_instance()

    @staticmethod
    def _user_kernel_dir_default():
        return pjoin(jupyter_data_dir(), 'kernels')

    @staticmethod
    def _kernel_dirs_default():
        dirs = jupyter_path('kernels')
        # # At some point, we should stop adding .ipython/kernels to the path,  TODO - seems like a good time.
        # # but the cost to keeping it is very small.
        # try:
        #     from IPython.paths import get_ipython_dir
        # except ImportError:
        #     try:
        #         from IPython.utils.path import get_ipython_dir
        #     except ImportError:
        #         # no IPython, no ipython dir
        #         get_ipython_dir = None
        # if get_ipython_dir is not None:
        #     dirs.append(os.path.join(get_ipython_dir(), 'kernels'))
        return dirs

    def find_kernel_specs(self, provider_id=DEFAULT_SPEC_PROVIDER):
        """Returns a dict mapping kernel names to resource directories for the given provider."""
        return self.cache.get_resource_dirs(provider_id=provider_id)

    def get_kernel_specs(self, provider_id=DEFAULT_SPEC_PROVIDER):
        """ Returns a dict mapping kernel names to specs for the given provider. """
        return self.cache.get_specs(provider_id=provider_id)

    def get_kernel_spec(self, kernel_name, provider_id=DEFAULT_SPEC_PROVIDER):
        """Returns a :class:`KernelSpec` instance for the given kernel_name.

        Raises :exc:`NoSuchKernel` if the given kernel name is not found.
        """
        return self.cache.get_spec(provider_id, kernel_name.lower())

    def get_all_specs(self, provider_id=DEFAULT_SPEC_PROVIDER):
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
        d = self.get_kernel_specs(provider_id=provider_id)
        return {kname: {
                "resource_dir": d[kname].resource_dir,
                "spec": d[kname]
                } for kname in d}

    def remove_kernel_spec(self, name, provider_id=DEFAULT_SPEC_PROVIDER):
        """Remove a kernel spec directory by name.

        Returns the path that was deleted.
        """
        specs = self.find_kernel_specs(provider_id=provider_id)
        spec_dir = specs[name]
        log.debug("Removing %s", spec_dir)
        if os.path.islink(spec_dir):
            os.remove(spec_dir)
        else:
            shutil.rmtree(spec_dir)

        return spec_dir

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
                stacklevel=2, )

        destination = self._get_destination_dir(kernel_name, user=user, prefix=prefix)
        log.debug('Installing kernelspec in %s', destination)

        kernel_dir = os.path.dirname(destination)
        if kernel_dir not in self.kernel_dirs:
            log.warning("Installing to %s, which is not in %s. The kernelspec may not be found.",
                        kernel_dir, self.kernel_dirs,)

        if os.path.isdir(destination):
            log.info('Removing existing kernelspec in %s', destination)
            shutil.rmtree(destination)

        shutil.copytree(source_dir, destination)
        log.info('Installed kernelspec %s in %s', kernel_name, destination)
        KernelSpecCache.get_instance()._refresh()  # Force a cache refresh
        return destination


def find_kernel_specs():
    """Returns a dict mapping kernel names to resource directories."""
    return KernelSpecManager().find_kernel_specs()


def get_kernel_spec(kernel_name):
    """Returns a :class:`KernelSpec` instance for the given kernel_name.

    Raises KeyError if the given kernel name is not found.
    """
    return KernelSpecManager().get_kernel_spec(kernel_name)


def install_kernel_spec(source_dir, kernel_name=None, user=False, replace=False,
                        prefix=None):
    return KernelSpecManager().install_kernel_spec(source_dir, kernel_name,
                                                   user, replace, prefix)


install_kernel_spec.__doc__ = KernelSpecManager.install_kernel_spec.__doc__
