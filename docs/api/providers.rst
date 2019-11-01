.. _kernel_provider_api:

Kernel Provider
===============

The Kernel Provider API is what a third-party would implement to introduce a form of
kernel management that might differ from the more common :class:`.KernelSpecProvider` kernel.
For example, a kernel provider might want to launch (and manage) kernels across a Kubernetes cluster.
They would then implement a provider that performs the necessary action for launch and provide
a :ref:`KernelManager <kernel_manager_api>` instance that can perform the appropriate actions to control
the kernel's lifecycle.

.. currentmodule:: jupyter_kernel_mgmt.discovery

.. seealso::
   :ref:`kernel_providers`

.. autoclass:: KernelProviderBase

   .. automethod:: find_kernels

   .. automethod:: launch

   .. automethod:: load_config

.. autoclass:: KernelSpecProvider

   .. automethod:: find_kernels
      :noindex:
   .. automethod:: launch
      :noindex:

.. autoclass:: IPykernelProvider

   .. automethod:: find_kernels
      :noindex:
   .. automethod:: launch
      :noindex:
