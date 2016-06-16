from bottle import route, template, request, post, Bottle, HTTPError, auth_basic
from pprint import pformat
from itertools import islice
from functools import wraps
import logging
import sys

log = logging.getLogger(__name__)

app = Bottle()


def _auth_basic(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        authfn = app.config.get("auth_basic_fn")
        if authfn:
            return auth_basic(authfn)(fn)(*args, **kwargs)
        else:
            return fn(*args, **kwargs)
    return wrapper


def set_runners(**name_runner_mapping):
    app.config["deploy.runners"] = name_runner_mapping

def set_auth_basic_fn(fn):
    app.config["auth_basic_fn"] = fn

def _get_runner(name):
    try:
        runners = app.config["deploy.runners"]
    except KeyError as e:
        sys.exit("you have to call set_runners first")

    return runners[name]

@app.route('/')
def status():
    tpl = """
    <html>
    <h1>Runners</h1>
    <ul>
      % for r in runners:
        <%
        bs = r.build_status[-1] if r.build_status else None
        %>
        <li>
        % if bs:
            <%
            date = bs.date.strftime("%Y-%m-%d %H:%M:%S %Z%z")
            %>

            <a href="{{r.name}}">{{r.name}}</a>:
            {{date}} - {{bs.msg}} - running: {{bs.running}} - ok: {{bs.ok}}
        % else:
            No job was ever running.
        % end
        </li>

      % end
    </ul>
    </html>
    """
    return template(tpl, runners=app.config["deploy.runners"].values())

@app.route('/<name>')
@_auth_basic
def runnerstatus(name):
    runner = _get_runner(name)
    rerun = "rerun" in request.query
    start = int(request.query.get("start", 0))
    end = int(request.query.get("end", 50))
    start = start if start >= 0 else 0
    end = end if end >= 0 else 0
    tpl = """
    <html>
    <h1>{{runner.name}} status events ({{start}} - {{end}}) --
    <a href={{runner.name}}/rerun>(re)start build</a></h1>
    <ul>
    % for bs in islice(reversed(bss),start,end):
        <%
        date = bs.date.strftime("%Y-%m-%d %H:%M:%S %Z%z")
        %>
        <li>{{date}} -- {{bs.msg}}
        <ul>
            <li>build still running: {{bs.running}}</li>
            <li>nothing went wrong: {{bs.ok}}</li>
            <li>message payload:<br>
                <pre>{{pformat(bs.payload, width=120)}}</pre>
            </li>
        </ul>
        </li>
    % end
    </ul>
    </html>
    """
    return template(tpl, runner=runner, bss=runner.build_status, islice=islice,
                    pformat=pformat, start=start, end=end)

@_auth_basic
@app.route('/<name>/rerun')
def rerun(name):
    runner = _get_runner(name)
    runner.build(abort_running=True, ignore_pull_error=True)
    return "Restarted the build"
