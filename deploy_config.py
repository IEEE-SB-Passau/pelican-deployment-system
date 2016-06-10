import os

if __name__ == "__main__":
    raise SystemExit("Not meant to be run directly!")

# make sure git does not block giving pw prompts
os.environ["GIT_TERMINAL_PROMPT"] = "0"

RUNNERS = {
    "website_master": {
        "working_directory": "/tmp/test",
        "clone_url": "https://github.com/catdog2/sandbox.git",
        "git_branch": "master",
        "target_directory": "/tmp/wwwout",
        "pelican_command": 'echo $PELICAN_SITEURL',
        "pelican_env": {"PELICAN_SITEURL": "//apu:800"}
    }
}
