Pelican-deploy
##############

A deployment daemon for pelican or other static site generators. Features:

* generating from the newest commit of a specified git branch
* cloning of a repository from a remote location and keep it up to date (supports submodules)
* cron like scheduled jobs
* github webhooks
* status page with optional http auth


How it works
------------

You can specify one or multiple runners. Each has a remote git repository (``clone_url``) 
specified wich will be cloned to the working directory and a branch (``git_branch``) within
that repository where the HEAD will be generated. 

The runners will be triggered either by scheduled jobs or by pushes to the repository.
The runners perform basically 3 steps:

1. the repository will be updated to the newest revision (or cloned at first)
2. a command will be run which generates the website (``build_command``) somewehere under 
   the working directory. (If you rely on a virtualenv you may want to use ``tox`` )
3. finally, after 2. completed successfully a command will be invoked (``final_install_command``)
   which installs the directory tree into the final location (e.g. the www root). 
   (``rsync`` is a nice tool for this). This procudure should avoid having a broken Website.

Installation
------------

``python 3.3+`` and ``git`` are required. 

The remaining dependencies are in requirements.txt, you can do ``pip install -r requirements.txt`` 
(you may want to setup a virtualenv for this, never do this as root).

Running
-------

First copy ``example_config.py`` to a place of your choice, then adjust it to your needs.

This program is a WSGI application which can run either standalone or may be integrated into any
WGSI compliant web server. For standalone mode, run ``./app.py </path/to/config.py> <listen address> <port>``.
If you want the WSGI app, call ``init_app(configpath)`` in ``app.py``.

Github webhooks
---------------

Point your github webhook to ``http://<listen address>:<port>/hooks/github/<runner_name>``, you need to define a 
hook for every runner.

Status Page
-----------

Under ``http://<listen address>:<port>/status/`` you will find a status page which informs about the 
state of the runners and a possibility to manually trigger a runner. May be protected by http basic auth but
in production you may want to use a dedicated web server for access control anyway.
