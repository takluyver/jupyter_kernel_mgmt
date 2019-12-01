.. _kernel_hl_api:

=====================
Kernel High Level API
=====================

The Kernel Management system exposes high level APIs that can be used by the consumer project. The async methods (not supported on Windows for now) are the recommended way to start and run a Kernel.

:class:`start_kernel_async <jupyter_kernel_mgmt.hl.start_kernel_async>`: Start a kernel by kernel type name. Returns a manager and a async client.

:class:`start_kernel_async <jupyter_kernel_mgmt.hl.run_kernel_async>`: Context manager to run a kernel by kernel type name. Returns an async client.

If the async is not supported on your platform, you may use the following blocking methods.

:class:`start_kernel_blocking <jupyter_kernel_mgmt.hl.start_kernel_blocking>`: Start a kernel by kernel type name. Returns a manager and a blocking client.

:class:`run_kernel_blocking <jupyter_kernel_mgmt.hl.run_kernel_blocking>`: Context manager to run a kernel by kernel type name. Returns a blocking client.
