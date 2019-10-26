.. _kernel_manager:

==============
Kernel Manager
==============

The :ref:`kernel manager <kernel_manager_api>` is the primary interface through which an application controls
a kernel's lifecycle upon its successful launch.  Implemented by the :ref:`provider <kernel_providers>`,
it exposes well-known methods to determine if the kernel is alive, as well as its interruption and shutdown,
among other things.  Applications like Jupyter Notebook invoke a majority of these methods indirectly via
the REST API upon a user's request, while others are invoked from within the application itself.