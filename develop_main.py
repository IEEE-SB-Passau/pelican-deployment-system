#! /usr/bin/env python3

from pelican_deploy import DeploymentRunner
from apscheduler.schedulers.background import BackgroundScheduler
from importlib.machinery import SourceFileLoader
import pelican_deploy.webhookbottle
import logging



if __name__ == "__main__":
    #for r in runners.values():
    #    r.build_blocking()

    config = SourceFileLoader("config", "deploy_config.py").load_module()

    runners = {name: DeploymentRunner(name, conf)
        for name, conf in config.RUNNERS.items()}

    # start a scheduler
    scheduler = BackgroundScheduler()
    scheduler.start()

    for i, (rname, trigger) in enumerate(config.SCHEDULED_BUILD_JOBS):
        scheduler.add_job(runners[rname].build, trigger=trigger,
                           name="{} ({})".format(i, rname))


    pelican_deploy.webhookbottle.set_runners(**runners)
    pelican_deploy.webhookbottle.set_github_secret(config.GITHUB_SECRET)
    pelican_deploy.webhookbottle.devrun()

