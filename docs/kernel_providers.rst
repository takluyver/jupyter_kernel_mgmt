.. _kernel_providers:

================
Kernel Providers
================


Creating a kernel provider
==========================

By writing a kernel provider, you can extend how Jupyter applications discover
and start kernels. For example, you could find kernels in an environment system
like conda, or kernels on remote systems which you can access.

To write a kernel provider, subclass
:class:`KernelProviderBase <jupyter_kernel_mgmt.discovery.KernelProviderBase>`, giving your provider an ID
and overriding two methods.

.. class:: MyKernelProvider

   .. attribute:: id

      A short string identifying this provider. Cannot contain forward slash
      (``/``).

   .. method:: find_kernels()

      Get the available kernel types this provider knows about.
      Return an iterable of 2-tuples: (name, attributes).
      *name* is a short string identifying the kernel type.
      *attributes* is a dictionary with information to allow selecting a kernel.
      This may also contain metadata describing other information pertaining to
      the kernel's launch - parameters, environment, etc.

   .. method:: launch(name, cwd=None, launch_params=None)
    
      Launches the kernel and returns a 2-tuple: (connection_info, kernel_manager).
      *connection_info* is a dictionary consisting of the connection information 
      pertaining to the launched kernel.
      *kernel_manager* is a :class:`KernelManager <.KernelManagerABC>` instance.

      *name* is a name returned from :meth:`find_kernels`.

      *cwd* is a string indicating the (optional) working directory in which the 
      kernel should be launched.

      *launch_params* is a dictionary of name/value pairs to be used by the provider
      and/or passed to the kernel as parameters.

For example, imagine we want to tell Jupyter about kernels for a new language
called *oblong*::

    # oblong_provider.py
    import asyncio
    from jupyter_kernel_mgmt.discovery import KernelProviderBase
    from jupyter_kernel_mgmt import KernelManager
    from shutil import which

    class OblongKernelProvider(KernelProviderBase):
        id = 'oblong'

        @asyncio.coroutine
        def find_kernels(self):
            if not which('oblong-kernel'):
                return  # Check it's available

            # Two variants - for a real kernel, these could be something like
            # different conda environments.
            yield 'standard', {
                'display_name': 'Oblong (standard)',
                'language': {'name': 'oblong'},
                'argv': ['oblong-kernel'],
            }
            yield 'rounded', {
                'display_name': 'Oblong (rounded)',
                'language': {'name': 'oblong'},
                'argv': ['oblong-kernel'],
            }

        async def launch(self, name, cwd=None, launch_params=None):
            if name == 'standard':
                return await my_launch_method(cwd=cwd, launch_params=launch_params,
                                             kernel_cmd=['oblong-kernel'],
                                             extra_env={'ROUNDED': '0'})
            elif name == 'rounded':
                return await my_launch_method(cwd=cwd, launch_params=launch_params,
                                             kernel_cmd=['oblong-kernel'],
                                             extra_env={'ROUNDED': '1'})
            else:
                raise ValueError("Unknown kernel %s" % name)

You would then register this with an *entry point*. In your ``setup.py``, put
something like this::

    setup(...
        entry_points = {
        'jupyter_kernel_mgmt.kernel_type_providers' : [
            # The name before the '=' should match the id attribute
            'oblong = oblong_provider:OblongKernelProvider',
        ]
    })

Finding kernel types
====================

To find and start kernels in client code, use
:class:`KernelFinder <jupyter_kernel_mgmt.discovery.KernelFinder>`. This uses multiple kernel
providers to find available kernels. Like a kernel provider, it has methods
``find_kernels`` and ``launch``. The kernel names it works
with have the provider ID as a prefix, e.g. ``oblong/rounded`` (from the example
above).

::

    from jupyter_kernel_mgmt.discovery import KernelFinder
    kf = KernelFinder.from_entrypoints()

    ## Find available kernel types
    for name, attributes in kf.find_kernels():
        print(name, ':', attributes['display_name'])
    # oblong/standard : Oblong (standard)
    # oblong/rounded : Oblong(rounded)
    # ...

    ## Start a kernel by name
    connect_info, manager = await kf.launch('oblong/standard')

    client = IOLoopKernelClient(connect_info, manager=manager)
    try:
        await asyncio.wait_for(client.wait_for_ready(), timeout=startup_timeout)
    except RuntimeError:
        await client.shutdown_or_terminate()
        await client.close()
        await manager.kill()

    # Use `manager` for lifecycle management, `client` for communication

.. _included_kernel_providers:

Included kernel providers
=========================

``jupyter_kernel_mgmt`` includes two kernel providers in its distribution.

1. :class:`KernelSpecProvider <jupyter_kernel_mgmt.discovery.KernelSpecProvider>` handles the discovery and launch
of most existing kernelspec-based kernels that exist today.

2. :class:`IPykernelProvider <jupyter_kernel_mgmt.discovery.IPykernelProvider>` handles the discover and launch
of any IPython kernel that is located in the executing python's interpreter.  For example, if the
application is running in a virtual Python environment, this provider identifies if any IPython
kernel is local to that environment and may not be identified by the path algorithm
used by :class:`KernelSpecProvider <jupyter_kernel_mgmt.discovery.KernelSpecProvider>`.

.. _included_launchers:

Included kernel launchers
=========================

The kernel provider is responsible for launching the kernel and returning the connection
information and :ref:`kernel manager <kernel_manager_api>` instance.  Typically, a provider
will implement a `launcher` to perform this action.

For those providers launching their kernels using the subprocess module's Popen class,
``jupyter_kernel_mgmt`` includes two kernel launcher implementations in its distribution.

1. :class:`SubprocessKernelLauncher <.SubprocessKernelLauncher>` launches kernels using
the 'tcp' transport.

2. :class:`SubprocessIPCKernelLauncher <.SubprocessIPCKernelLauncher>` launchers kernels using
the 'ipc' transport (using filesystem sockets).

Both launchers return the resulting connection information and an instance of
:class:`KernelManager <.KernelManager>`, which is subsequently used to manage the
rest of the kernel's lifecycle.


Glossary
========

Kernel instance
  A running kernel, a process which can accept ZMQ connections from frontends.
  Its state includes a namespace and an execution counter.

Kernel type
  The software to run a kernel instance, along with the context in which a
  kernel starts. One kernel type allows starting multiple, initially similar
  kernel instances. For instance, one kernel type may be associated with one
  conda environment containing ``ipykernel``. The same kernel software in
  another environment would be a different kernel type. Another software package
  for a kernel, such as ``IRkernel``, would also be a different kernel type.

Kernel provider
  A Python class to discover kernel types and allow a client to start instances
  of those kernel types. For instance, one kernel provider might find conda
  environments containing ``ipykernel`` and allow starting kernel instances in
  these environments.  While another kernel provider might enable the ability
  to launch kernels across a Kubernetes cluster.

.. _provider_id:

Provider Id
  A simple string ([a-z,0-9,_,-,.]) that identifies the provider.  Each kernel
  name returned from the provider's :meth:`find_kernels` method will be prefixed
  by the provider id followed by a `'/'` separator.
