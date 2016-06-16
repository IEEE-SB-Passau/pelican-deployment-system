#! /usr/bin/env python3

from pelican_deploy import DeploymentRunner
from apscheduler.schedulers.background import BackgroundScheduler
from importlib.machinery import SourceFileLoader
from operator import methodcaller
from bottle import run, default_app
from wsgiref.simple_server import make_server
import pelican_deploy.webhookbottle
import pelican_deploy.statusbottle
import logging
import atexit
import sys

def init_app(configpath):

    config = SourceFileLoader("config", configpath).load_module()

    runners = {name: DeploymentRunner(name, conf)
               for name, conf in config.RUNNERS.items()}

    for r in runners.values():
        atexit.register(r.shutdown)  # finally, wait for builds to finish

    for r in runners.values():
        atexit.register(r.try_abort_build)  # then try to abort running builds

    schedulers = {r: BackgroundScheduler(daemon=True) for r in runners}
    for s in schedulers.values():
        s.start()
        atexit.register(s.shutdown, wait=False)  # first stop the schedulers

    atexit.register(print,
                    "<><><><><><><><><><><><><><><><><><><><><><><><><>\n",
                    ">>>>> Shutting down gracefully, please wait! <<<<<\n",
                    "<><><><><><><><><><><><><><><><><><><><><><><><><>",
                    file=sys.stderr, sep="")

    for i, (rname, trigger) in enumerate(config.SCHEDULED_BUILD_JOBS):
        schedulers[rname].add_job(runners[rname].build,
                                  trigger=trigger,
                                  name="{} ({})".format(rname, i),
                                  id="{}_{}".format(rname, i),
                                  max_instances=1,
                                  kwargs={"wait": True,
                                         "ignore_pull_error": True})

    pelican_deploy.webhookbottle.set_runners(**runners)
    pelican_deploy.webhookbottle.set_github_secret(config.GITHUB_SECRET)
    default_app().mount("/hooks/", pelican_deploy.webhookbottle.app)

    pelican_deploy.statusbottle.set_auth_basic_fn(getattr(config,
                                                  "STATUS_AUTH_BASIC_FN", None))
    pelican_deploy.statusbottle.set_runners(**runners)
    default_app().mount("/status/", pelican_deploy.statusbottle.app)

    return default_app()

if __name__ == "__main__":
    if (len(sys.argv) != 4):
        print("Usage: {} <configfile> <host> <port>".format(sys.argv[0]))
        sys.exit(1)
    _, configpath, host, port = sys.argv

    app = init_app(configpath)
    run(app=app, host=host, port=port, debug=True)
