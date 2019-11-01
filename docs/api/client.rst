.. _kernel_client_api:

Kernel Client
=============

The Kernel Client API is how an application communicates with a previously
launched kernel using the :doc:`Jupyter message protocol (FIXME jupyter_protocol) <jupyter_client:messaging>`.
For applications based on IO loops, Jupyter Kernel Management provides :class:`.IOLoopKernelClient`.

.. currentmodule:: jupyter_kernel_mgmt.client_base

.. autoclass:: KernelClient
   :members:

.. currentmodule:: jupyter_kernel_mgmt.client

.. autoclass:: IOLoopKernelClient
   :members:
   :inherited-members:
