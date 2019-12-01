.. _kernel_finder:

================
Kernel Finder
================

The ``jupyter_kernel_mgmt`` package provides a means of discovering kernel types
that are available for use. This is accomplished using the
:class:`KernelFinder <jupyter_kernel_mgmt.discovery.KernelFinder>` class.

:class:`KernelFinder <jupyter_kernel_mgmt.discovery.KernelFinder>` instances are
created in one of two ways.

1. The most common way is to call KernelFinder's class method
   :meth:`.KernelFinder.from_entrypoints()`.
   This loads all registered kernel providers.

2. You can also provide a list of :doc:`kernel provider <kernel_providers>`
   instances to KernelFinder's constructor.
   This loads only those instances provided.

Once an instance of :class:`KernelFinder <jupyter_kernel_mgmt.discovery.KernelFinder>` has
been created, kernels can be discovered and launched via KernelFinder's
instance methods, :meth:`find_kernels() <.KernelFinder.find_kernels>` and
:meth:`launch() <.KernelFinder.launch>`, respectively.

Finding kernels
===============

Available kernel types are discovered using KernelFinder's
:meth:`.KernelFinder.find_kernels()` method.  This method is a generator that walks
the set of loaded kernel providers calling each of their
:meth:`KernelProvider.find_kernels() <.KernelProviderBase.find_kernels()>` methods
yielding each entry.

Each kernel type has an ID (e.g. ``spec/python3``) and a dictionary containing
information to help a program or a user select an appropriate kernel.
Different providers may include different metadata in this dictionary.

.. _kernelspecs:

Kernel Specifications
---------------------

The main built-in kernel provider,
:class:`~.jupyter_kernel_mgmt.discovery.KernelSpecProvider`,
looks for kernels described by files in certain specific folders.
Each kernel is described by one directory, and the name of the directory is
used in its kernel type ID.
These kernel spec directories may be in a number of locations:

+--------+-------------------------------------------+-----------------------------------+
|  Type  | Unix                                      | Windows                           |
+========+===========================================+===================================+
| System | ``/usr/share/jupyter/kernels``            | ``%PROGRAMDATA%\jupyter\kernels`` |
|        |                                           |                                   |
|        | ``/usr/local/share/jupyter/kernels``      |                                   |
+--------+-------------------------------------------+-----------------------------------+
| User   | ``~/.local/share/jupyter/kernels`` (Linux)| ``%APPDATA%\jupyter\kernels``     |
|        |                                           |                                   |
|        | ``~/Library/Jupyter/kernels`` (Mac)       |                                   |
+--------+-------------------------------------------+-----------------------------------+
|  Env   |                         ``{sys.prefix}/share/jupyter/kernels``                |
+--------+-------------------------------------------+-----------------------------------+


The user location takes priority over the system locations, and the case of the
names is ignored, so selecting kernels works the same way whether or not the
filesystem is case sensitive.

Since kernel names, and their :ref:`provider ids <provider_id>`, show up in URLs and other places,
a kernelspec is required to have a simple name, only containing ASCII letters, ASCII numbers, and the simple separators: ``-`` hyphen, ``.`` period, ``_`` underscore.

Other locations may also be searched if the :envvar:`JUPYTER_PATH` environment
variable is set.

For IPython kernels, three types of files are presently used:
``kernel.json``, ``kernel.js``, and logo image files. However, different Kernel Providers
can support other files and directories within the kernel directory or may not even
use a directory for their kernel discovery model.  That said, for kernels prior
to Kernel Providers or those discovered by instances of class
:class:`.KernelSpecProvider`, the most important
file is **kernel.json**. This file consists of a JSON-serialized dictionary
that adheres to the :ref:`kernel specification format <kernelspec_format>`.


For example, the kernel.json file for the IPython kernel looks like this::

    {
     "argv": ["python3", "-m", "IPython.kernel",
              "-f", "{connection_file}"],
     "display_name": "Python 3",
     "language": "python"
    }


.. _kernelspec_format:

Kernel Specification Format
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The information contained in each entry returned from a Kernel Provider's
:meth:`find_kernels() <.KernelProviderBase.find_kernels>` method consists of a
dictionary containing the following keys and values:

- **display_name**: The kernel's name as it should be displayed in the UI.
  Unlike the kernel name used in the API, this can contain arbitrary unicode
  characters.  This value should be provided by all kernel providers.
- **language**: The name of the language of the kernel.
  When loading notebooks, if no matching kernelspec key (may differ across machines)
  is found, a kernel with a matching `language` will be used.
  This allows a notebook written on any Python or Julia kernel to be properly
  associated with the user's Python or Julia kernel, even if they aren't listed
  under the same name as the author's. This value should be provided by all kernel providers.
- **metadata** (optional): A dictionary of additional attributes about this
  kernel. Metadata added here should be namespaced for the tool reading and
  writing that metadata.

Kernelspec-based providers obtain this information from a `kernel.json` file located in a
directory pertaining to the kernel's name.  Other fields in the kernel.json file include
information used to launch and manage the kernel.  As a result, you'll also find the following
fields in `kernel.json` files:

- **argv**: (optional): A list of command line arguments used to start the kernel. For
  instances of class :class:`KernelSpecProvider <jupyter_kernel_mgmt.discovery.KernelSpecProvider>` the text
  ``{connection_file}`` in any argument will be replaced with the path to the
  connection file.  However, subclasses of :class:`KernelSpecProvider <jupyter_kernel_mgmt.discovery.KernelSpecProvider>`
  may choose to provide different substitutions, especially if they don't use a connection file.
- **interrupt_mode** (optional): May be either ``signal`` or ``message`` and
  specifies how a client is supposed to interrupt cell execution on this kernel,
  either by sending an interrupt ``signal`` via the operating system's
  signalling facilities (e.g. `SIGINT` on POSIX systems), or by sending an
  ``interrupt_request`` message on the control channel (see
  :ref:`kernel interrupt <jupyter_protocol:msging_interrupt>`).
  If this is not specified ``signal`` mode will be used.
- **env** (optional): A dictionary of environment variables to set for the kernel.
  These will be added to the current environment variables before the kernel is
  started.

However, whether a provider exposes information used during their kernel's
launch is entirely up to the provider.

IPython kernel provider
-----------------------

A second built-in kernel provider,
:class:`~.jupyter_kernel_mgmt.discovery.IPykernelProvider`, identifies if
``ipykernel`` is importable by the same Python the frontend is running on.
If so, it provides exactly one kernel type, ``pyimport/kernel``, which runs the
IPython kernel in that same Python environment.

This may be functionally a duplicate of a kernel type discovered through an
:ref:`installed kernelspec <kernelspecs>`.


Launching kernels
=================

Launching kernels works similarly to their discovery.  To launch a previously discovered kernel,
the kernel's `fully qualified kernel type` is provided to KernelFinder's
:meth:`launch() <jupyter_kernel_mgmt.discovery.KernelFinder.launch>` method.

.. note::
   A **fully qualified kernel type** includes a prefix of the kernel's :ref:`provider id <provider_id>` followed by a
   forward slash ('/').  For example, the ``python3`` kernel as provided by the
   :class:`KernelSpecProvider <jupyter_kernel_mgmt.discovery.KernelSpecProvider>`
   would have a fully qualified kernel type of ``spec/python3``.

   The application is responsible for ensuring the name passed to
   :meth:`KernelFinder.launch() <.KernelFinder.launch>` is prefixed with a provider id.  For backwards
   compatibility with existing kernelspecs, a prefix of ``spec/`` is recommended in such cases so as to associate it with
   the ``KernelSpecProvider``.

KernelFinder's launch method then locates the provider and calls the specific kernel provider's
:meth:`launch() <jupyter_kernel_mgmt.discovery.KernelProviderBase.launch>` method.

:py:meth:`KernelFinder.launch(name, cwd=None, launch_params=None) <jupyter_kernel_mgmt.discovery.KernelProviderBase.launch>`
takes two additional (and optional) arguments.

**cwd** (optional) specifies the current working directory relative to the notebook.
Use of this value is up to the provider, as some kinds of kernels may not see
the same filesystem as the process launching them.

**launch_params** (optional) specifies a dictionary of provider-specific name/value pairs that can can
be used during the kernel's launch.  What parameters are used can also be specified in the form of JSON
schema embedded in the provider's kernel specification returned from its
:meth:`find_kernels() <.KernelProviderBase.find_kernels>` method.  The application retrieving the kernel's
information and invoking its subsequent launch, is responsible for providing appropriately relevant values.


Using launched kernels
----------------------
A 2-tuple of :ref:`connection information <jupyter_protocol:connection_files>` and the provider's
:class:`kernel manager <jupyter_kernel_mgmt.managerabc.KernelManagerABC>` instance are returned
from KernelFinder's launch method.

Although the :ref:`KernelManager <kernel_manager>` instance allows an application to manage a kernel's lifecycle, it
does not provide a means of communicating with the kernel.  To communicate with the kernel, an
instance of :ref:`KernelClient <kernel_client>` is required.

If the application would like to perform automatic
restart operations (where the application detects the kernel is no longer running and issues a
restart request) the application should establish a :ref:`KernelRestarter <kernel_restarter>` instance.
