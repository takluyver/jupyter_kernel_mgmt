# Use with Jupyter Server

This page describes the way [Jupyter Server](https://github.com/jupyter/jupyter_server) uses the Kernel Management module.

![](./images/kernel_mgmt_server.svg "")

On the Jupyter Server side, each WEB handlers (located in services/kernels/handlers: MainKernelHandler, KernelHandler, KernelActionHandler, ZMQChannelHandler) have:

- A kernel_manager. The default manager is `jupyter_server.services.kernels.kernelmanager.MappingKernelManager`.
- A kernel_finder. The default is `jupyter_kernel_mgmt.discovery.KernelFinder` which is imported from the jupyter_kernel_mgmt library.

Jupyter Server runs with a single `ServerApp` built around a `SessionManager`. The SessionManager uses a `MappingKernelManager`. All instances of MappingKernelManager have a `KernelFinder`.

The [included providers](kernel_providers.html#included-kernel-providers) (KernelSpecProvider and IPykernelProvider) register their entrypoints.

```
entrypoints:
 jupyter_kernel_mgmt.kernel_type_providers' : [
  'spec = jupyter_kernel_mgmt.discovery:KernelSpecProvider',
  'pyimport = jupyter_kernel_mgmt.discovery:IPykernelProvider',
]
```

External Providers can register their own entypoints (e.g the [kubernetes_kernel_provider](https://github.com/gateway-experiments/kubernetes_kernel_provider) which extends the [remote_kernel_provider](https://github.com/gateway-experiments/remote_kernel_provider)).

The interactions sequence between Jupyter Server and the Kernel Management is shown here.

![](./images/kernel_mgmt_server_sequence.svg "")
