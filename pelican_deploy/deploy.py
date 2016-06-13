from pathlib import Path
from collections import namedtuple
from pelican_deploy.gittool import Repo, log_git_result
from functools import partial
from subprocess import Popen, PIPE
from pelican_deploy.util import exception_logged
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
import sys
import logging
import shlex
import os
import atexit

log = logging.getLogger(__name__)

log_git = partial(log_git_result, out_logger=log.debug,
                  err_logger=log.debug, status_logger=log.debug)

BUILD_REPO_DIR = "{name}_build_repo"
OUTPUT_DIR = "{name}_output"


class DeploymentRunner:

    def __init__(self, name, runner_config):
        self.name = name
        self.working_directory = Path(runner_config["working_directory"])
        if not self.working_directory.exists():
            log.info("creating working directory for %s: %s", name,
                     self.working_directory)
            self.working_directory.mkdir(parents=True)
        self.working_directory = self.working_directory.resolve()

        self.clone_url = runner_config["clone_url"]
        self.git_branch = runner_config["git_branch"]
        self.build_repo_path = self.working_directory / BUILD_REPO_DIR.format(
            name=name)
        outdir = self.working_directory / OUTPUT_DIR.format(name=name)
        self.build_command = runner_config["build_command"].format(
            output=outdir)
        self.final_install_command = runner_config["final_install_command"]\
            .format(output=outdir)

        self._build_proc_env = dict(os.environ,
                                    **runner_config.get("build_env", {}))

        self._executor = ThreadPoolExecutor(max_workers=1)
        self._futures = set()
        self._build_proc = None
        self._abort = False
        self._build_lock = RLock()
        self._repo_update_lock = RLock()

    def update_build_repository(self):
        with self._repo_update_lock:
            self._update_build_repository()

    def _update_build_repository(self):
        if not self.build_repo_path.exists():
            self.build_repo_path.mkdir(parents=True)

        repo = Repo(str(self.build_repo_path))
        if not repo.is_repo():
            if self.build_repo_path.is_dir() and \
                    next(self.build_repo_path.iterdir(), None) is not None:
                log.error(
                    "non-empty %s exists but not a valid git repository!",
                    self.build_repo_path)
                raise RuntimeException(("non-empty {} exists but not a"
                    "valid git repository!").format(self.build_repo_path))
            else:
                log.info("Build repository %s not there, cloning",
                         self.build_repo_path)
                result = repo.clone("--branch", self.git_branch,
                                    "--depth", "1", self.clone_url, ".")
                log_git(result)


        origin_url = repo.config_get("remote.origin.url")
        if origin_url != self.clone_url:
            log.info("%s build_repo: URL of git origin changed (`%s` --> `%s`),\
                     adjusting...", self.name, origin_url, self.clone_url)
            repo.config("remote.origin.url", self.clone_url)

        # deinit submodules to avoid removed ones dangling around later
        # they should stay around in .git, so reinit should be fast
        result = repo.submodule("deinit", "--force", ".")
        log_git(result)

        result = repo.checkout("--force", self.git_branch)
        log_git(result)

        result = repo.reset("--hard")
        log_git(result)

        log.info("%s build_repo: pulling changes from origin", self.name)
        refspec = "+{b}:{b}".format(b=self.git_branch)
        result = repo.pull("--force", "--no-edit", "--recurse-submodules",
                           "--depth", "1", "origin", refspec)
        log_git(result)

        try:
            result = repo.clean("--force", "-d", "-x")
            log_git(result)
        except:
            log.warning("git clean failed!", exc_info=True)

        # update the submodules
        log.info("%s build_repo: update submodules", self.name)
        result = repo.submodule("update", "--init", "--force", "--recursive")
        log_git(result)

    def build(self, abort_running=False, wait=False):
        with self._build_lock:
            if abort_running:
                self.try_abort_build()

            # cancel everything, so we are next
            for fut in self._futures.copy():
                fut.cancel()
                if fut.done():
                    self._futures.remove(fut)

            build_func = exception_logged(self.build_blocking, log.error)
            future = self._executor.submit(build_func)
            self._futures.add(future)
        if wait:
            return future.result()

    def try_abort_build(self):
        proc = self._build_proc
        self._abort = True
        if proc:
            proc.kill()

    def final_install(self):
        args = shlex.split(self.final_install_command)
        log.info("%s: Starting final_install `%s`", self.name, args)
        proc = Popen(args, stdout=PIPE, stderr=PIPE, universal_newlines=True)
        atexit.register(proc.kill)
        outs, errs = proc.communicate()
        status = proc.wait()
        atexit.unregister(proc.kill)

        if status < 0:
            log.info("%s: killed final_install_command (%s)", self.name, status)
        else:
            log.info("%s: finished final_install_command with status %s!",
                        self.name, status)
            log.info('%s final_install_command stdout: %s\n', self.name, outs)
            log.info('%s final_install_command stderr: %s\n', self.name, errs)

        if status > 0:
            log.error("%s: final_install failed! Website may be broken!",
                      self.name)

    def build_blocking(self):
        self._abort = False

        # preparing build environment
        self.update_build_repository()
        # TODO: prepare_output()

        # start the build if we should not abort
        if not self._abort:
            args = shlex.split(self.build_command)
            log.info("%s: Starting build_command `%s`", self.name, args)
            self._build_proc = Popen(args, stdout=PIPE, stderr=PIPE,
                                     cwd=str(self.build_repo_path),
                                     env=self._build_proc_env,
                                     universal_newlines=True)
            atexit.register(self._build_proc.kill)
            outs, errs = self._build_proc.communicate()
            status = self._build_proc.wait()
            atexit.unregister(self._build_proc.kill)

            if status < 0:
                log.info("%s: killed build_command", self.name)
            else:
                log.info("%s: finished build_command with status %s!",
                         self.name, status)
                log.info('%s build_command stdout: %s\n', self.name, outs)
                log.info('%s build_command stderr: %s\n', self.name, errs)
            if status == 0:
                self.final_install()
