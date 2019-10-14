"""Testing utils for jupyter_client tests

"""
import asyncio
import json
import os
pjoin = os.path.join
import pytest
import sys


skip_win32 = pytest.mark.skipif(sys.platform.startswith('win'), reason="Windows")


@pytest.fixture
def setup_env(tmpdir, monkeypatch):
    monkeypatch.setenv('JUPYTER_CONFIG_DIR', pjoin(tmpdir.dirname, 'jupyter'))
    monkeypatch.setenv('JUPYTER_DATA_DIR', pjoin(tmpdir.dirname, 'jupyter_data'))
    monkeypatch.setenv('JUPYTER_RUNTIME_DIR', pjoin(tmpdir.dirname, 'jupyter_runtime'))
    monkeypatch.setenv('IPYTHONDIR', pjoin(tmpdir.dirname, 'ipython'))


def execute(code='', kc=None, **kwargs):
    """wrapper for doing common steps for validating an execution request"""
    from .test_message_spec import validate_message
    if kc is None:
        kc = KC
    msg_id = kc.execute(code=code, **kwargs)
    reply = kc.get_shell_msg(timeout=TIMEOUT)
    validate_message(reply, 'execute_reply', msg_id)
    busy = kc.get_iopub_msg(timeout=TIMEOUT)
    validate_message(busy, 'status', msg_id)
    assert busy['content']['execution_state'] == 'busy'

    if not kwargs.get('silent'):
        execute_input = kc.get_iopub_msg(timeout=TIMEOUT)
        validate_message(execute_input, 'execute_input', msg_id)
        assert execute_input['content']['code'] == code

    return msg_id, reply['content']


def run_sync(coro_method):
    return asyncio.get_event_loop().run_until_complete(coro_method)


sample_kernel_json = {'argv':['cat', '{connection_file}'],
                      'display_name':'Test kernel',
                      'metadata': {}
                     }


def install_sample_kernel(kernels_dir, kernel_name='sample', kernel_file='kernel.json', kernel_json=sample_kernel_json):
    """install a sample kernel in a kernels directory"""
    sample_kernel_dir = pjoin(kernels_dir, kernel_name)
    os.makedirs(sample_kernel_dir, exist_ok=True)
    json_file = pjoin(sample_kernel_dir, kernel_file)
    with open(json_file, 'w') as f:
        json.dump(kernel_json, f)
    return sample_kernel_dir
