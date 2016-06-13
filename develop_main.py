#! /usr/bin/env python3

from pelican_deploy import DeploymentRunner
from apscheduler.schedulers.background import BackgroundScheduler
from importlib.machinery import SourceFileLoader
from operator import methodcaller
from bottle import run, default_app
import pelican_deploy.webhookbottle
import logging



if __name__ == "__main__":

    config = SourceFileLoader("config", "deploy_config.py").load_module()

    runners = {name: DeploymentRunner(name, conf)
        for name, conf in config.RUNNERS.items()}

    #for r in runners.values():
    #    print(r.build(wait=True))

    schedulers = {r: BackgroundScheduler(daemon=False) for r in runners}
    for s in schedulers.values():
        s.start()

    for i, (rname, trigger) in enumerate(config.SCHEDULED_BUILD_JOBS):
        schedulers[rname].add_job(runners[rname].build, trigger=trigger,
                          name="{} ({})".format(rname, i),
                          id="{}_{}".format(rname, i), max_instances=1,
                          kwars={"wait" : True})



    pelican_deploy.webhookbottle.set_runners(**runners)
    pelican_deploy.webhookbottle.set_github_secret(config.GITHUB_SECRET)
    default_app().mount("/hooks/", pelican_deploy.webhookbottle.app)

    run(host='0.0.0.0', port=4000, debug=True)

