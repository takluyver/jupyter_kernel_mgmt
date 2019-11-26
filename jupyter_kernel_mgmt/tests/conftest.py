import os
import pytest
from ..util import _init_asyncio_patch

pjoin = os.path.join


@pytest.fixture
def asyncio_patch():
    _init_asyncio_patch()


@pytest.fixture
def setup_env(tmpdir, monkeypatch, asyncio_patch):
    monkeypatch.setenv('JUPYTER_CONFIG_DIR', pjoin(tmpdir.dirname, 'jupyter'))
    monkeypatch.setenv('JUPYTER_DATA_DIR', pjoin(tmpdir.dirname, 'jupyter_data'))
    monkeypatch.setenv('JUPYTER_RUNTIME_DIR', pjoin(tmpdir.dirname, 'jupyter_runtime'))
    monkeypatch.setenv('IPYTHONDIR', pjoin(tmpdir.dirname, 'ipython'))

