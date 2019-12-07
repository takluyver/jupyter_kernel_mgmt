.. _changelog:

==============================
Changes in Jupyter Kernel Mgmt
==============================

0.5.1
-----

- Enable support for python 3.5

0.5.0
-----

- Tolerate missing status on kernel-info-reply
- Add some missing dependencies and min versions
- Force pin of pyzmq for travis builds, increase timeout
- Close kernel client in start_new_kernel tests
- Give kernel providers opportunity to load configuration
- Add support for kernel launch parameters
- Add support for native coroutines (async def) 
- Significant documentation updates
- Fix operations on Windows
- Rework high-level APIs

0.4.0
-----

- Remove unused import
- Make test fail because of idle-handling bug
- Fix watching for idle after execution
- Allow multiple providers to use kernelspec-based configurations
- Allow multiple providers to use kernelspec-based configurations

0.3.0
-----

- Expose kernel_info_dict on blocking kernel client
- Translate tornado TimeoutError to base Python TimeoutError for blocking client
- Normalise contents of kernel info dicts
- Remove configurable kernel spec class and whitelist
- Remove deprecated method to install IPython kernel spec
- Remove special kernelspec handling for IPython
- Get rid of LoggingConfigurable base class
- Allow passing a different search path for KernelSpecProvider
- Catch unparseable kernelspecs when finding all
- Rework restarter events
- Don't try to relaunch a dead kernel with the same ports 
- Rework message handlers API
- Use tornado event loop to dispatch restart callbacks
- Allow restarter to be used for manual restarts
- Support Python 3.4, missing JSONDecodeError

0.2.0
-----

- Add kernel_info_dict attribute
- Don't use prerelease versions of test dependencies
- Return message even if status='error'
- Remove ErrorInKernel exception

0.1.1
-----

- Initial experimental implementation.


Note: Because the code in this repository originated from jupyter_client you may 
also want to look at its `changelog history <https://jupyter-client.readthedocs.io/en/latest/changelog.html>`_.
