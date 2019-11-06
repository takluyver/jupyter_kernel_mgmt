.. _server:

=======================
Use with Jupyter Server
=======================

This page describes the way `Jupyter Server <https://github.com/jupyter/jupyter_server>`_ uses the Kernel Management module.

.. image:: ./images/kernel_mgmt_server.svg

On the Jupyter Server side, each WEB handlers located in services/kernels/handlers: 

- MainKernelHandler
- KernelHandler
- KernelActionHandler
- ZMQChannelHandler
- MainKernelSpecHandler

Each of these handlers have:

- A ``kernel_manager`` - the default manager is `MappingKernelManager` provided by `jupyter_server`.
- A ``kernel_finder`` - which is imported from the `jupyter_kernel_mgmt` library

Jupyter Server runs with a single `ServerApp` built around a ``SessionManager``. The SessionManager uses a ``MappingKernelManager``. All instances of MappingKernelManager have a ``KernelFinder``.

The :ref:`included kernel providers <included_kernel_providers>` (:class:`KernelSpecProvider <jupyter_kernel_mgmt.discovery.KernelSpecProvider>` and :class:`IPykernelProvider <jupyter_kernel_mgmt.discovery.IPykernelProvider>`) register their entrypoints.

.. code-block:: python

  entrypoints:
    jupyter_kernel_mgmt.kernel_type_providers' : [
      'spec = jupyter_kernel_mgmt.discovery:KernelSpecProvider',
      'pyimport = jupyter_kernel_mgmt.discovery:IPykernelProvider',
    ]

External Providers can register their own entypoints, e.g the `kubernetes_kernel_provider <https://github.com/gateway-experiments/kubernetes_kernel_provider>`_ which extends the `remote_kernel_provider <https://github.com/gateway-experiments/remote_kernel_provider>`_.

The interactions sequence between Jupyter Server and the Kernel Management is sketched here.

.. image:: ./images/kernel_mgmt_server_sequence.svg
