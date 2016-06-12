from bottle import route, run, template, request, post, Bottle, HTTPError
import logging
import hmac
import hashlib
import sys

log = logging.getLogger(__name__)

app = Bottle()


def set_runners(**name_runner_mapping):
    app.config["deploy.runners"] = name_runner_mapping

def set_github_secret(secret):
    app.config["deploy.github_secret"] = secret

def _get_runner(name):
    try:
        runners = app.config["deploy.runners"]
    except KeyError as e:
        sys.exit("you have to call set_runners first")

    return runners[name]

def _start_build(name, push_ref):
    runner = _get_runner(name)
    branch = runner.git_branch
    if push_ref in (branch, "refs/heads/{}".format(branch)):
        runner.build(abort_running=True)
    else:
        log.debug("Runner %s was not invoked, push to branch %s, runner for %s",
                  runner.name, push_ref, branch)

def _verify_github_signature(sighdr, body):
    try:
        secret = app.config["deploy.github_secret"]
    except KeyError as e:
        raise RuntimeError("github secret not set!") from e

    signature = 'sha1=' + hmac.new(secret, body, hashlib.sha1).hexdigest()
    return hmac.compare_digest(sighdr, signature)


@app.post('/github/<name>')
def index(name):
    sighdr = request.headers.get("X-Hub-Signature", "")
    if not _verify_github_signature(sighdr, request.body.read()):
        log.error("Github request for %s faild to validate. "
                  "Have you configured the secret correctly?", name)
        raise HTTPError(status=403)

    evtype = request.headers.get('X-GitHub-Event')
    if evtype != "push":
        log.info("Github sent event of type %s to %s, ignoring", evtype, name)
        return "Ignored"

    log.info("Got Github event of type %s to %s", evtype, name)

    hook = request.json

    _start_build(name, hook.get("ref", ""))
    return "Success!"

def devrun():
    run(app=app, host='0.0.0.0', port=4000, debug=True)
