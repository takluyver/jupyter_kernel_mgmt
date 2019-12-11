from __future__ import division

import os
import shutil
from subprocess import Popen, PIPE
import sys
from tempfile import mkdtemp
import time
import json


def _launch(extra_env):
    env = os.environ.copy()
    env.update(extra_env)
    return Popen([sys.executable, '-c',
                  'from jupyter_kernel_mgmt.kernelapp import main; main()'],
                 env=env, stderr=PIPE)


WAIT_TIME = 20
POLL_FREQ = 10


def test_kernelapp_lifecycle(setup_env):
    # Check that 'jupyter kernel' starts and terminates OK.
    runtime_dir = os.getenv('JUPYTER_RUNTIME_DIR')  # already temp via setup_env fixture
    startup_dir = mkdtemp()
    started = os.path.join(startup_dir, 'started')
    try:
        p = _launch({'JUPYTER_CLIENT_TEST_RECORD_STARTUP_PRIVATE': started,
                    })
        # Wait for start
        for _ in range(WAIT_TIME * POLL_FREQ):
            if os.path.isfile(started):
                break
            time.sleep(1 / POLL_FREQ)
        else:
            raise AssertionError("No started file created in {} seconds"
                                 .format(WAIT_TIME))

        # Connection file should be there by now
        # TODO: now there are 2 connection files (1 to launch the kernel, 1 to
        # advertise it). Clean this up when we have a better solution.
        files = os.listdir(runtime_dir)
        assert len(files) == 2
        for cf in files:
            assert cf.startswith('kernel')
            assert cf.endswith('.json')

        # since the connection file is no longer displayed by the application
        # (connection info is dumped instead), we'll open the connection file
        # and pick out the entry for hb_port, then build an applicably-formatted
        # string to assert it's in stderr.

        connection_file = os.path.join(runtime_dir, cf)
        with open(connection_file) as file:
            connection_info = json.load(file)
            hb_port_info = "'hb_port': " + str(connection_info['hb_port'])

        # Send SIGTERM to shut down
        p.terminate()
        _, stderr = p.communicate(timeout=WAIT_TIME)
        assert hb_port_info in stderr.decode('utf-8', 'replace')
    finally:
        shutil.rmtree(startup_dir)

