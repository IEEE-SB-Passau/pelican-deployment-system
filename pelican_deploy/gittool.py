import os
import shlex
from collections import namedtuple
from subprocess import Popen, PIPE

CmdResult = namedtuple("CmdResult", "status stdout stderr")

class Repo:
    def __init__(self, repo_dir, git_cmd="git", default_timeout=None):
        self.repo_dir = repo_dir
        self.git_cmd = git_cmd
        self.default_timeout = default_timeout

    def __getattr__(self, name):
        name = name.replace("_", "-")
        def cmdcaller(*args, cmd=None, **kwargs):
            cmdargs = shlex.split(cmd) if cmd else args
            return self.cmd(*((self.git_cmd, name) + tuple(cmdargs)), **kwargs)
        return cmdcaller

    def cmd(self, *args, timeout=None, env=None):
        timeout = timeout if timeout else default_timeout
        proc = self.popen_cmd(*args, env=env)
        outs, errs = proc.communicate(timeout=timeout)
        status = proc.wait()
        return CmdResult(status, outs, errs)

    def popen_cmd(self, *args, env=None):
        return Popen(args, stdout=PIPE, stderr=PIPE, cwd=self.repo_dir, env=env)

    def is_bare(self):
        result = self.rev_parse("--is-bare-repository")
        return result.stdout.startswith(b"true")

    def is_repo(self):
        return self.rev_parse("--git-dir").status == 0

