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

from pathlib import Path
from collections import namedtuple, deque
from pelican_deploy.gittool import Repo, log_git_result
from functools import partial
from subprocess import Popen, PIPE, check_call
from pelican_deploy.util import exception_logged
from concurrent.futures import ThreadPoolExecutor
from threading import RLock, Thread
from datetime import datetime
import pytz
import sys
import logging
import shlex
import os

log = logging.getLogger(__name__)

log_git = partial(log_git_result, out_logger=log.debug,
                  err_logger=log.debug, status_logger=log.debug)

TOX_RESULT_FILE = "{name}_result.json"
BUILD_REPO_DIR = "{name}_build_repo"
OUTPUT_DIR = "{name}_output"
STATUS_LEN = 500

BuildStatus = namedtuple("BuildStatus", "date ok msg payload running")

class PullError(Exception):
    pass

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
        toxresult = self.working_directory / TOX_RESULT_FILE.format(name=name)
        self.build_command = runner_config["build_command"].format(
            output=outdir, toxresult=toxresult)
        self.final_install_command = runner_config["final_install_command"]\
            .format(output=outdir)
        self._output_dir = outdir

        self._build_proc_env = dict(os.environ,
                                    **runner_config.get("build_env", {}))

        self._executor = ThreadPoolExecutor(max_workers=1)
        self._futures = set()
        self._build_proc = None
        self._abort = False
        self._build_lock = RLock()
        self._repo_update_lock = RLock()

        self.build_status = deque(maxlen=STATUS_LEN)

    def clean_working_dir(self, abort_running=True):
        Thread(target=self.clean_working_dir_blocking).start()

    def clean_working_dir_blocking(self, abort_running=True):
        def clean_fn():
            rmpaths = [str(self.build_repo_path), str(self._output_dir)])
            for p in rmpaths:
                check_call(["rm", "-rf"] + p)

        with self._build_lock:
            if abort_running:
                self.try_abort_build()

            # cancel everything, so we are next
            for fut in self._futures.copy():
                fut.cancel()
                if fut.done():
                    self._futures.remove(fut)

            def build_job():
                log.info("Starting cleaning of working dir!")
                self.update_status(True, "Starting cleaning of working dir!",
                                       running=False)
                try:
                    exception_logged(clean_fn, log.error)()
                except Exception as e:
                    self.update_status(False, "Cleaning failed!",
                                       running=False, payload={"exception": e})
                    raise

            future = self._executor.submit(build_job)
            self._futures.add(future)
            future.result()
            log.info("Working dir cleand!")
            self.update_status(True, "Working dir cleand!", running=False)

    def update_status(self, ok, msg, payload=None, running=True):
        date = pytz.utc.localize(datetime.utcnow())
        self.build_status.append(BuildStatus(date, ok, msg, payload, running))

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
                raise RuntimeError(("non-empty {} exists but not a"
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
        try:
            result = repo.pull("--force", "--recurse-submodules",
                               "--depth", "1", "origin", refspec)
            log_git(result)
        except Exception as e:
            # need to reinit the submodules
            self._update_build_repo_submodules(repo)
            raise PullError from e

        try:
            result = repo.clean("--force", "-d", "-x")
            log_git(result)
        except:
            log.warning("git clean failed!", exc_info=True)

        # update the submodules
        self._update_build_repo_submodules(repo)

    def _update_build_repo_submodules(self, repo):
        log.info("%s build_repo: update submodules", self.name)
        results = repo.submodule_sync_update_init_recursive_force()
        for r in results:
            log_git(r)

    def build(self, abort_running=False, wait=False, ignore_pull_error=False,
               build_fn=None):
        with self._build_lock:
            if abort_running:
                self.try_abort_build()

            # cancel everything, so we are next
            for fut in self._futures.copy():
                fut.cancel()
                if fut.done():
                    self._futures.remove(fut)

            build_bl = partial(self._build_blocking, ignore_pull_error=
                                   ignore_pull_error)
            build_fn = build_fn if build_fn else build_bl

            def build_job():
                build_func = exception_logged(build_fn, log.error)
                try:
                    build_func()
                except Exception as e:
                    self.update_status(False, "Build stopped with exception",
                                       running=False, payload={"exception": e})
                    raise

            future = self._executor.submit(build_job)
            self._futures.add(future)
        if wait:
            return future.result()

    def try_abort_build(self):
        proc = self._build_proc
        self._abort = True
        if proc:
            try:
                proc.kill()
            except:
                log.debug("unable to kill", exc_info=True)

    def final_install(self):
        args = shlex.split(self.final_install_command)
        self.update_status(True, "Starting final_install",
                           payload={"cmd": args})
        log.info("%s: Starting final_install `%s`", self.name, args)
        proc = Popen(args, stdout=PIPE, stderr=PIPE, universal_newlines=True,
                     start_new_session=True)
        outs, errs = proc.communicate()
        status = proc.wait()

        if status < 0:
            log.info("%s: killed final_install_command (%s)", self.name, status)
        else:
            log.info("%s: finished final_install_command with status %s!",
                        self.name, status)
            log.info('%s final_install_command stdout: %s\n', self.name, outs)
            log.info('%s final_install_command stderr: %s\n', self.name, errs)

        if status > 0:
            self.update_status(False, ("final_install_command failed."
                               " Website may be broken!"),
                               payload={"status": status,
                                        "stdout": outs, "stderr": errs})
            log.error("%s: final_install failed! Website may be broken!",
                      self.name)
        else:
            self.update_status(True, "finished final_install_command",
                               payload={"stdout": outs, "stderr": errs})

    def _build_blocking(self, ignore_pull_error=False):
        self._abort = False

        # preparing build environment
        try:
            self.update_status(True, "Start updating repository")
            self.update_build_repository()
        except PullError:
            if ignore_pull_error:
                msg = "Git pull failed, trying to continue with what we have"
                self.update_status(False, msg)
                log.warning(msg, exc_info=True)
            else:
                raise

        # start the build if we should not abort
        if not self._abort:
            args = shlex.split(self.build_command)
            self.update_status(True, "Starting the main build command",
                               payload={"cmd": args})
            log.info("%s: Starting build_command `%s`", self.name, args)
            self._build_proc = Popen(args, stdout=PIPE, stderr=PIPE,
                                     cwd=str(self.build_repo_path),
                                     env=self._build_proc_env,
                                     universal_newlines=True,
                                     start_new_session=True)
            outs, errs = self._build_proc.communicate()
            status = self._build_proc.wait()
            self._build_proc = None

            if status < 0:
                self.update_status(False, "killed build_command")
                log.info("%s: killed build_command", self.name)
            else:
                log.info("%s: finished build_command with status %s!",
                         self.name, status)
                log.info('%s build_command stdout: %s\n', self.name, outs)
                log.info('%s build_command stderr: %s\n', self.name, errs)
            if status == 0:
                self.update_status(True, "finished build_command",
                                   payload={"stdout": outs, "stderr": errs})
                self.final_install()
            else:
                self.update_status(False, "build_command failed",
                                   payload={"status": status,
                                   "stdout": outs, "stderr": errs})

            self.update_status(self.build_status[-1].ok, "End of build",
                               running=False)


    def shutdown(self):
        self.try_abort_build()
        self._executor.shutdown(wait=True)
