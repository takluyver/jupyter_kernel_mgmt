.. _kernel_manager_api:

Kernel Manager
==============

The Kernel Manager API is used to manage a kernel's lifecycle.  It does not provide
communication support between the application and the kernel itself.  Any third-parties
implementing their own :class:`KernelProvider <.KernelProviderBase>` would likely
implement their own ``KernelManager`` derived from the :class:`.KernelManagerABC` abstract base class.
However, those providers using :ref:`Popen to launch local kernels <included_launchers>`
can use :class:`KernelManager <.KernelManager>` directly.

.. currentmodule:: jupyter_kernel_mgmt.managerabc

.. autoclass:: KernelManagerABC

   .. attribute:: kernel_id

      The id associated with the kernel.

   .. automethod:: is_alive

   .. automethod:: wait

   .. automethod:: signal

   .. automethod:: interrupt

   .. automethod:: kill

   .. automethod:: cleanup

.. currentmodule:: jupyter_kernel_mgmt.subproc.manager

.. autoclass:: KernelManager
   :inherited-members:
