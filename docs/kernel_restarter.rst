.. _kernel_restarter:

================
Kernel Restarter
================

Applications that wish to perform automatic restart operations (where the application
detects the kernel is no longer running and issues a restart request) use a
:ref:`kernel restarter <kernel_restarter_api>`.  This instance is associated to
the appropriate :ref:`kernel manager <kernel_manager_api>` instance to accomplish
the restart functionality.