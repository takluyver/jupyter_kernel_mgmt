"""Testing utils for jupyter_client tests

"""
import asyncio
import json
import os
pjoin = os.path.join
import sys


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
