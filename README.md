# Jupyter Kernel management

This is an experimental refactoring of the machinery for launching
and using Jupyter kernels.

Some notes on the components, and how they differ from their counterparts in
`jupyter_client`:


### KernelClient

Communicate with a kernel over ZeroMQ sockets.

Conceptually quite similar to the KernelClient in `jupyter_client`, but the
implementation differs a bit:

* Shutting down a kernel nicely has become a method on the client, since it
  is primarily about sending a message and waiting for a reply.
* The main client class now uses a Tornado IOLoop, and the blocking interface
  is a wrapper around this. This avoids writing mini event loops which discard
  any message but the one they're looking for.
* Message (de)serialisation and sending/receiving are now part of the separate
  `jupyter_protocol` package.

### KernelManager

Do 'subproccess-ish' things to a kernel - knowing if it has died, interrupting
with a signal, and forceful termination.

Greatly reduced in scope relative to `jupyter_client`. In particular, the
manager is no longer responsible for launching a kernel: that machinery has
been separated (see below). The plan is to have parallel async managers, but I
haven't really worked this out yet.

The main manager to work with a subprocess is in `jupyter_kernel_mgmt.subproc.manager`.
I have an implementation using the Docker API in my separate `jupyter_docker_kernels` package.
ManagerClient also implements the manager interface (see below).

### KernelNanny and ManagerClient

`KernelNanny` will expose the functionality of a manager using more ZMQ
sockets, which I have called `nanny_control` and `nanny_events`.

`ManagerClient` wraps the network communications back into the KernelManager
Python interface, so a client can use it as the manager for a remote kernel.
It probably needs a better name.

### Discovering and launching kernels

A *kernel type* may be, for instance, Python in a specific conda environment.
Each kernel type has an ID, e.g. `spec/python3` or `ssh/mydesktop`.

The plan is that third parties can implement different ways of finding
kernel types. They expose a *kernel provider*, which would know about e.g.
conda environments in general and how to find them.

Kernel providers written so far:

- Finding kernel specs (in this repository)
- Finding `ipykernel` in the Python we're running on (in this repository)
- Explicitly listed kernels available over SSH (https://github.com/takluyver/jupyter_ssh_kernels/)
- Explicitly listed kernels in Docker containers (https://github.com/takluyver/jupyter_docker_kernels/)

The common interface to providers is `jupyter_kernel_mgmt.discovery.KernelFinder`.

To launch a kernel, you pass its type ID to the launch method:

```python
from jupyter_kernel_mgmt.discovery import KernelFinder
kf = KernelFinder.from_entrypoints()
connection_info, manager = kf.launch('spec/python3')
```

This returns the connection info dict (to be used by a client) and an optional
manager object. If `manager` is None, the connection info should include
sockets for a kernel nanny, so `ManagerClient` can be used. For now, it's
possible to have neither.

### Automatically restarting kernels

TODO, see issue #1.
