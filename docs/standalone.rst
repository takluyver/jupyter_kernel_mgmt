.. _standalone:

================
Standalone Usage
================

The aim of the Kernel Management is to be integrated in larger applications such as the :ref:`Jupyter Server <server>`.

Although, it can be used as a standalone module to, for example, launch a :ref:`Kernel Finder <kernel_finder>`
from the command line and get a list of :ref:`Kernel Specifications <kernelspecs>`

.. code-block:: python

    python -m jupyter_kernel_mgmt.discovery

Similarly to `jupyter_client <https://github.com/jupyter/jupyter_client>`_, the Kernel Management can be used in different flavors and use cases.
We are looking to your contributions to enrich the example use cases.
You can get inspiration from the `test_client.py <https://github.com/takluyver/jupyter_kernel_mgmt/blob/master/jupyter_kernel_mgmt/tests/test_client.py>`_ source code.

PS: The existing separated `jupyter_client <https://github.com/jupyter/jupyter_client>`_ can not be used in combination with the Kernel Management.
The :ref:`KernelClient <kernel_client>` code to use should be the one shipped by Kernel Management, not by `jupyter_client <https://github.com/jupyter/jupyter_client>`_.
