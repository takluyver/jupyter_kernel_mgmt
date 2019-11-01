.. _kernel_restarter_api:

Kernel Restarter
================

The Kernel Restarter API is used by applications wishing to perform automatic kernel
restarts upon detection of the kernel's unexpected termination.  ``jupyter_kernel_mgmt`` provides
:class:`.KernelRestarterBase` and provides an implementation of that class for Tornado-based
applications via :class:`.TornadoKernelRestarter`.

.. currentmodule:: jupyter_kernel_mgmt.restarter

.. autoclass:: KernelRestarterBase

   .. attribute:: debug

      Whether to include every poll event in debugging output.  Has to be set
      explicitly, because there will be *a lot* of output.

   .. attribute:: time_to_dead

      Kernel heartbeat interval in seconds.

   .. attribute:: restart_limit

      The number of consecutive autorestarts before the kernel is presumed dead.

   .. automethod:: start

   .. automethod:: stop

   .. automethod:: add_callback

   .. automethod:: remove_callback

   .. automethod:: do_restart

   .. automethod:: poll

.. autoclass:: TornadoKernelRestarter
   :inherited-members:
   :members:
