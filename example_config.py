
   Copyright 2016 Peter Dahlberg

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

import os
import logging
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

if __name__ == "__main__":
    raise SystemExit("Not meant to be run directly!")

def _rsync_cmd(dest):
    cmd = ("rsync --delete-delay --recursive --times --stats "
           "'{output}/' '{dest}'")
    return cmd.format(dest=dest, output="{output}")

# configure the logger
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

# make sure git does not block giving pw prompts, git 2.3+ only
os.environ["GIT_TERMINAL_PROMPT"] = "0"
os.environ["GIT_ASKPASS"] = "echo" # also to avoid interactiveness
os.environ["GIT_EDITOR"] = "true" # also to avoid interactiveness
os.environ["GIT_PAGER"] = "cat" # also to avoid interactiveness
# avoid system config, we want default behaviour
os.environ["GIT_CONFIG_NOSYSTEM"] = "yes"

# needs to be a byte like object
GITHUB_SECRET = b"changetosomethingrandomlong"

RUNNERS = {
    # unique name of the runner, avoid spaces and other obscure characters
    "website_master": {

        # directory where building takes place, will be created if not there
        # multiple runners may point to the same one
        "working_directory": "/tmp/test",

        # upstream url of the repository which contains the website
        # use https://git::@github.com... to avoid pw prompts and instead fail
        # (e.g. if github gives errornously 401 temporarily, git would block)
        # os.environ["GIT_TERMINAL_PROMPT"] = "0" does the same but git 2.3+only
        "clone_url": "https://git::@github.com/IEEE-SB-Passau/pelican-ieee-passau.git",

        # branch which will be built
        "git_branch": "master",

        # command which installs the generated directory tree to it's final
        # destination (the wwwroot) e.g. rsync. {output} will be replaced by
        # the path to the generator output
        "final_install_command": _rsync_cmd("/tmp/testroot"),

        # command which builds the website
        # important: specify {output} as output path of the generator
        # if you use toy you may use {toxresult} as the path to the result.json
        "build_command": ('tox -e pelican --result-json "{toxresult}" '
                          '--recreate -- -d --output "{output}"'),

        # will be added to env when running build_command
        "build_env": {"PELICAN_SITEURL": "//apu:800"}
    }
}

# define crojobs as sequence of (runner, trigger) pairs, for cron triggers see
# http://apscheduler.readthedocs.io/en/latest/modules/triggers/cron.html
SCHEDULED_BUILD_JOBS = [
    ("website_master", CronTrigger(minute="*/30")),
    ("website_master", DateTrigger()) # once at start

]

# user, pass for /status/... subpages, if not set or None no auth is done
def STATUS_AUTH_BASIC_FN(user, passw):
    return user == "powerpoint" and passw == "karaoke"

