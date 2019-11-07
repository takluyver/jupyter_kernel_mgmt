.. _server:

=======================
Use with Jupyter Server
=======================

This page describes the way `Jupyter Server <https://github.com/jupyter/jupyter_server>`_ uses the Kernel Management module.

.. image:: ./images/kernel_mgmt_server.svg

On the Jupyter Server side, WEB handlers receive the javascript requests and are responsible for the communication with the Kernel Manager and Providers.

The MainKernelSpecHandler in `services/kernelsspecs/handlers` manages the findings of the Kernel Specs.

The other Handlers located in `services/kernels/handlers` manage the launch :

- MainKernelHandler
- KernelHandler
- KernelActionHandler
- ZMQChannelsHandler

Jupyter Server runs with a single `ServerApp` that initializes each of the handlers with services, specifically for the Kernels:

- A ``kernel_manager`` - the default manager is `MappingKernelManager` provided by `jupyter_server`.
- A ``kernel_finder`` - which is imported from the `jupyter_kernel_mgmt` library.
- A ``session_manager`` - which a uses a kernel_manager ``MappingKernelManager``.

All instances of MappingKernelManager have a ``KernelFinder`` field.

Notably, the ZMQChannelsHandler has access to a kernel_client field (the kernel_client is created with `kernel_manager.get_kernel(self.kernel_id).client`).

In order be found by a kernel_finder, Kernel Providers need to register them selves via the entrypoint mechanism.

The :ref:`included kernel providers <included_kernel_providers>` (:class:`KernelSpecProvider <jupyter_kernel_mgmt.discovery.KernelSpecProvider>` and :class:`IPykernelProvider <jupyter_kernel_mgmt.discovery.IPykernelProvider>`) register by default their entrypoints.

.. code-block:: python

  entrypoints:
    jupyter_kernel_mgmt.kernel_type_providers' : [
      'spec = jupyter_kernel_mgmt.discovery:KernelSpecProvider',
      'pyimport = jupyter_kernel_mgmt.discovery:IPykernelProvider',
    ]

The system administrator can install additional providers.
In that case, those external providers can register their own entypoints, see e.g `kubernetes_kernel_provider <https://github.com/gateway-experiments/kubernetes_kernel_provider>`_, `yarn_kernel_provider <https://github.com/gateway-experiments/yarn_kernel_provider>`_...

The interactions sequence between Jupyter Server and the Kernel Management is sketched here.
Please note that this diagram just gives an idea of the interactions and is not aimed to reflect an exhaustive list of object constructs nor method calls...

.. image:: ./images/kernel_mgmt_server_sequence.svg
