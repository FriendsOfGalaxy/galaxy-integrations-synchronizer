import pathlib
import json
import os
from invoke import task, exceptions
import sys
import subprocess
import contextlib


GITHUB = 'https://github.com'
FOG = 'FriendsOfGalaxy'
FOG_EMAIL = 'friendsofgalaxy@gmail.com'
FILES_TO_EXCLUDE = ['README.md', '.travis.yml']
FOG_BASE_BRANCH = 'master'
PR_BRANCH = 'autoupdate'

TEST_FORK_NAME = 'test-integration-fork'
TEST_UPSTREAM = 'FriendsOfGalaxyTester/test-integration'
TEST_MANIFEST_LOCATION = 'manifest.json'
TEST_RELEASE_BRANCH = 'master'


@contextlib.contextmanager
def chdir(dirname=None):
    curdir = os.getcwd()
    try:
        if dirname is not None:
            os.chdir(dirname)
        yield
    finally:
        os.chdir(curdir)


def get_version(abs_path):
    with open(abs_path, 'r') as f:
        return json.load(f)['version']


def init(c):
    res = c.run(f"git clone {GITHUB}/{FOG}/{fork_name}")
    with chdir(str(fork_dir)):
        c.run(f'git config user.name {FOG}')
        c.run(f'git config user.email {FOG_EMAIL}')

        c.run(f'git remote add upstream {GITHUB}/{upstream}')
        # try:
        #     c.run(f'git remote add origin {GITHUB}/{FOG}/{fork_name}')
        # except exceptions.UnexpectedExit:   # todo check default
        c.run(f'git remote set-url origin {GITHUB}/{FOG}/{fork_name}')


@task
def create_branch(c, name=PR_BRANCH):
    c.run(f'git checkout {PR_BRANCH} || git checkout -b {PR_BRANCH} && git pull origin {PR_BRANCH}', warn=True)
    c.run(f'git branch {name}')
    c.run(f'git push --set-upstream origin {name}')


@task
def sync(c, fork_name=TEST_FORK_NAME, upstream=TEST_UPSTREAM, release_branch=TEST_RELEASE_BRANCH, manifest_location=TEST_MANIFEST_LOCATION):
    """Requires env variable GITHUB_TOKEN (for hub) to not be prompt with password
    :param fork_name: name of current git name fork
    :upstream: github <user/repo_name> pattern
    "release_branch: branch to be checked for new updates
    :manifest_location: from root
    """
    root = pathlib.Path()
    fork_dir = root / fork_name

    if not fork_dir.exists():
        c.run(f"inv init")

    with chdir(str(fork_dir)):
        c.run('git fetch upstream')
        c.run(f'git checkout {PR_BRANCH} || git checkout -b {PR_BRANCH} && git pull origin {PR_BRANCH}', warn=True)
        c.run(f'git push --set-upstream origin {PR_BRANCH}')

        print(f'merging latest release branch {release_branch}')
        c.run(f'git merge --no-commit --no-ff upstream/{release_branch}')

        print('excluding reserved files')
        c.run(f'git checkout {FOG_BASE_BRANCH} -- {" ".join(FILES_TO_EXCLUDE)}', warn=True)

        c.run(f'git commit -m "Merged upstream"', warn=True)  # TODO rm warn

        # TODO generate manifest if not exists
        manifest_abs_path = os.path.abspath(os.path.normpath(manifest_location))
        version = get_version(manifest_abs_path)
        print('preparing pull-request for version', version)
        pr_title = f"Version {version}"
        pr_message = "Sync with the original repository"
        try:
            c.run(
                f'hub pull-request --push --base {FOG}:{FOG_BASE_BRANCH} --head {FOG}:{PR_BRANCH} '
                f'-m "{pr_title}" -m "{pr_message}" --labels autoupdate --browse'
            )
        except Exception as e:
            print(e)