.. _kernel_launcher_api:

Kernel Launchers
================

The kernel provider is responsible for launching the kernel and returning the connection
information and :ref:`kernel manager <kernel_manager_api>` instance.  For those providers
choosing to use Popen as their means of launching their kernels, ``jupyter_kernel_mgmt`` provides
:class:`.SubprocessKernelLauncher` for the 'tcp' transport and and :class:`.SubprocessIPCKernelLauncher`
for the 'ipc' transport (using filesystem sockets).

.. currentmodule:: jupyter_kernel_mgmt.subproc.launcher

.. autoclass:: SubprocessKernelLauncher
   :members:

.. autoclass:: SubprocessIPCKernelLauncher
   :members: