.. _hl_api:

High Level API
==============

These functions are convenient interfaces to start and interact with Jupyter
kernels.

Async interface
---------------

These functions are meant to be called from an asyncio event loop.

.. autoclass:: jupyter_kernel_mgmt.run_kernel_async

.. autofunction:: jupyter_kernel_mgmt.start_kernel_async

Blocking interface
------------------

.. autofunction:: jupyter_kernel_mgmt.run_kernel_blocking

.. autofunction:: jupyter_kernel_mgmt.start_kernel_blocking
