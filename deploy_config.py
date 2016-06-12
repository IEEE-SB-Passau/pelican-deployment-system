import os

if __name__ == "__main__":
    raise SystemExit("Not meant to be run directly!")

# make sure git does not block giving pw prompts, git 2.3+ only
os.environ["GIT_TERMINAL_PROMPT"] = "0"

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

        # the final target, usually the wwwroot
        "target_directory": "/tmp/wwwout",

        # command which builds the website
        # important: specify {output} as output path of the generator
        "build_command": 'tox -e pelican --recreate -- --output "{output}"',

        # will be added to env when running build_command
        "build_env": {"PELICAN_SITEURL": "//apu:800"}
    }
}
