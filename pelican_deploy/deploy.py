from pathlib import Path
from collections import namedtuple
from git import Repo, InvalidGitRepositoryError, NoSuchPathError
from subprocess import Popen
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
import sys
import logging
import shlex
import os
import atexit

log = logging.getLogger(__name__)

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
        self.target_directory = runner_config["target_directory"]
        self.build_repo_path = self.working_directory / BUILD_REPO_DIR.format(
            name=name)
        self.pelican_command = runner_config["pelican_command"].format(
            output=OUTPUT_DIR.format(name=name))
        self._build_proc_env = dict(os.environ,
                                    **runner_config.get("pelican_env", {}))

        self._executor = ThreadPoolExecutor(max_workers=1)
        self._futures = set()
        self._build_proc = None
        self._abort = False
        self._build_lock = RLock()

    def update_build_repository(self):
        try:
            build_repo = Repo(str(self.build_repo_path))

        except (InvalidGitRepositoryError, NoSuchPathError) as e:
            if self.build_repo_path.is_dir() and \
                    next(self.build_repo_path.iterdir(), None) is not None:
                log.error(
                    "non-empty %s exists but not a valid git repository!",
                    self.build_repo_path)
                raise
            else:
                log.info("Build repository %s not there, cloneing", e)
                build_repo = Repo.clone_from(self.clone_url,
                                             str(self.build_repo_path),
                                             branch=self.git_branch)

        if build_repo.remotes.origin.url != self.clone_url:
            cw = build_repo.remotes.origin.config_writer
            cw.set("url", self.clone_url)
            cw.release()

        build_repo.head.reference = build_repo.create_head(self.git_branch)
        assert not build_repo.head.is_detached

        # deinit submodules to avoid removed ones dangling around later
        # they should stay around in .git, so reinit should be fast
        build_repo.git.submodule("deinit", ".")

        build_repo.remotes.origin.pull(
            force=True,
            no_edit=True,
            refspec="+{b}:{b}".format(b=self.git_branch),
            recurse_submodules="yes")

        # forcefully reset the working tree
        build_repo.head.reset(index=True, working_tree=True)
        try:
            build_repo.git.clean(force=True)
        except:
            log.warning("git clean failed!", exc_info=True)

        # update the submodules
        build_repo.git.submodule("update", "--init", "--force", "--recursive")

    def build(self, abort_running=False):
        with self._build_lock:
            if abort_running:
                self.try_abort_build()

            # cancel everything, so we are next
            for fut in self._futures.copy():
                fut.cancel()
                if fut.done():
                    self._futures.remove(fut)

            self._futures.add(self._executor.submit(self.build_blocking))

    def try_abort_build(self):
        proc = self._build_proc
        self._abort = True
        if proc:
            proc.kill()

    def build_blocking(self):
        self._abort = False

        # preparing build environment
        self.update_build_repository()
        # TODO: prepare_output()

        # start the build if we should not abort
        if not self._abort:
            args = shlex.split(self.pelican_command)
            self._build_proc = Popen(args,
                                     cwd=str(self.build_repo_path),
                                     env=self._build_proc_env)
            atexit.register(self._build_proc.kill)
            status = self._build_proc.wait()
            atexit.unregister(self._build_proc.kill)

            if status == 0:
                # TODO: postproc...
                pass
