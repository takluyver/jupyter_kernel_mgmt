Jupyter Kernel Management |version|
===================================

This package provides the Python API for starting, managing and communicating with
Jupyter kernels.
For information on messaging with Jupyter kernels, please
refer to the `Jupyter Protocol documentation <https://jupyter-protocol.readthedocs.io/en/latest/index.html>`_.

.. note::
   This is a new interface under development, and may still change.
   Not all Jupyter applications use this yet.
   See the `jupyter_client <https://pexpect.readthedocs.io/en/latest/>`_ docs for the established way of
   discovering and managing kernels.

.. toctree::
   :maxdepth: 2
   :caption: Application Developers

   kernel_finder
   kernel_manager
   kernel_client
   kernel_restarter
   standalone
   server

..  seealso::
    :doc:`api/hl`

.. toctree::
   :maxdepth: 2
   :caption: Kernel Provider Developers

   kernel_providers

.. toctree::
   :maxdepth: 2
   :caption: API

   api/index

.. toctree::
    :maxdepth: 2
    :caption: Changes

    changelog


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
