# Standalone Usage

The aim of the Kernel Management is to be integrated in larger application such as [Jupyter Server](./server).

Although, it can be used a standalone module to, for example, launch a [Kernel Finder](./kernel_finder) from the command line and get a list of [Kernel Specs](./kernel_finder.html#kernel-specifications).

```python
# !!! This is failing for now...
# Follow https://github.com/takluyver/jupyter_kernel_mgmt/issues/27 for a fix.
python -m jupyter_kernel_mgmt.discovery
```
