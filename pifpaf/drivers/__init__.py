# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import os
import signal
import subprocess
import threading

import fixtures


LOG = logging.getLogger(__name__)


class Driver(fixtures.Fixture):
    def __init__(self):
        super(Driver, self).__init__()
        self.env = {}

    def _setUp(self):
        self.tempdir = self.useFixture(fixtures.TempDir()).path
        self.putenv("PIFPAF_DATA", self.tempdir)

    @staticmethod
    def get_parser(parser):
        return parser

    def putenv(self, key, value):
        self.env[key] = value
        return self.useFixture(fixtures.EnvironmentVariable(key, value))

    def _kill(self, pid, signal=signal.SIGTERM):
        return os.kill(pid, signal)

    def _kill_pid_file(self, pidfile):
        with open(pidfile, "r") as f:
            pid = int(f.read().strip())
        self._kill(pid)

    @staticmethod
    def find_config_file(filename):
        for d in ("/usr/local/etc",
                  "/etc",
                  os.path.expanduser("~/.local/etc"),
                  os.getenv("VIRTUAL_ENV", "") + "/etc"):
            fullpath = os.path.join(d, filename)
            if os.path.exists(fullpath):
                return fullpath
        raise RuntimeError("Configuration file `%s' not found" % filename)

    @staticmethod
    def _read_in_bg(app, fd):
        while True:
            data = fd.readline()
            if not data:
                break
            LOG.debug("%s output: %s", app, data.rstrip())

    def _exec(self, command, stdout=False, ignore_failure=False,
              stdin=None, wait_for_line=None, path=[]):
        LOG.debug("executing: %s" % command)

        app = command[0]

        if stdout or wait_for_line:
            stdout_fd = subprocess.PIPE
        else:
            # TODO(jd) Need to close at some point
            stdout_fd = open(os.devnull, 'w')

        if stdin:
            stdin_fd = subprocess.PIPE
        else:
            # TODO(jd) Need to close at some point
            stdin_fd = open(os.devnull, 'r')

        if path:
            env = {
                "PATH": ":".join(path) + ":" + os.getenv("PATH", ""),
            }
        else:
            env = None

        c = subprocess.Popen(
            command,
            close_fds=True,
            stdin=stdin_fd,
            stdout=stdout_fd,
            stderr=subprocess.STDOUT,
            env=env)

        if stdin:
            LOG.debug("%s input: %s" % (app, stdin))
            c.stdin.write(stdin)
            c.stdin.close()

        if stdout or wait_for_line:
            lines = []
            while True:
                line = c.stdout.readline()
                LOG.debug("%s output: %s", app, line.rstrip())
                if not line:
                    if wait_for_line:
                        raise RuntimeError(
                            "Program did not print: `%s'"
                            % wait_for_line)
                    break
                lines.append(line)
                if wait_for_line and wait_for_line in line:
                    break
            # Continue to read
            t = threading.Thread(target=self._read_in_bg,
                                 args=(app, c.stdout,))
            t.setDaemon(True)
            t.start()
            stdout_str = b"".join(lines)
        else:
            stdout_str = None

        if not wait_for_line:
            status = c.wait()
            assert(ignore_failure or status == 0)

        return c, stdout_str

    def _touch(self, fname):
        open(fname, 'a').close()
        os.utime(fname, None)
