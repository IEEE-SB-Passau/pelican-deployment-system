#! /usr/bin/env python3

import deploy_config
from pelican_deploy import DeploymentRunner
import pelican_deploy.webhookbottle
import logging


runners = {name: DeploymentRunner(name, conf)
           for name, conf in deploy_config.RUNNERS.items()}

if __name__ == "__main__":
    #for r in runners.values():
    #    r.build_blocking()
    pelican_deploy.webhookbottle.set_runners(**runners)
    pelican_deploy.webhookbottle.set_github_secret(deploy_config.GITHUB_SECRET)
    pelican_deploy.webhookbottle.devrun()

