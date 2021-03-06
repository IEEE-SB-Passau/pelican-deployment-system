#   Copyright 2016 Peter Dahlberg
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import os
import errno
import shlex
from collections import namedtuple
from subprocess import Popen, PIPE

CmdResult = namedtuple("CmdResult", "cmd status stdout stderr")

class GitCommandError(Exception):
    def __init__(self, message, result, *args, **kwargs):
        super().__init__(message, result, *args, **kwargs)
        self.result = result


class Repo:
    def __init__(self, repo_dir, git_cmd="git", default_timeout=None):
        if not os.path.exists(repo_dir):
            raise FileNotFoundError(errno.ENOENT, "Path, does not exist",
                                    repo_dir)
        self.repo_dir = repo_dir
        self.git_cmd = git_cmd
        self.default_timeout = default_timeout

    def __getattr__(self, name):
        name = name.replace("_", "-")
        def cmdcaller(*args, cmd=None, **kwargs):
            cmdargs = shlex.split(cmd) if cmd else args
            return self.cmd(*((self.git_cmd, name) + tuple(cmdargs)), **kwargs)
        return cmdcaller

    def cmd(self, *args, timeout=None, env=None, universal_newlines=True,
            errors_raise=True):
        timeout = timeout if timeout else self.default_timeout
        proc = self.popen_cmd(*args, env=env)
        outs, errs = proc.communicate(timeout=timeout)
        status = proc.wait()
        res = CmdResult(args,status, outs, errs)
        if status != 0 and errors_raise:
            raise GitCommandError("git failed: {}".format(args), res)
        return res

    def popen_cmd(self, *args, env=None, universal_newlines=True):
        return Popen(args, stdout=PIPE, stderr=PIPE, cwd=self.repo_dir, env=env,
                     universal_newlines=universal_newlines,
                     start_new_session=True)

    def is_bare(self):
        result = self.rev_parse("--is-bare-repository")
        return result.stdout.startswith("true")

    def is_repo(self):
        return self.rev_parse("--git-dir", errors_raise=False).status == 0

    def config_get(self, key):
        res = self.config("--get", key)
        return res.stdout.rstrip("\r\n")

def log_git_result(result, out_logger=None, err_logger=None, status_logger=None):
    if status_logger:
        err_logger('%s exit status: %s', result.cmd, result.status)
    if out_logger:
        out_logger('git stdout:\n%s', result.stdout)
    if err_logger:
        err_logger('git stderr:\n%s', result.stderr)



