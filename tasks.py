import pathlib
import json
import os
from invoke import task, exceptions
import sys
import subprocess
import contextlib


GITHUB = 'https://github.com'
FOG = 'FriendsOfGalaxy'
FILES_TO_EXCLUDE = ['README.md', '.travis.yml']
FOG_BASE_BRANCH = 'master'

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


@task
def sync(c, fork_name=TEST_FORK_NAME, upstream=TEST_UPSTREAM, release_branch=TEST_RELEASE_BRANCH, manifest_location=TEST_MANIFEST_LOCATION):
    """Requires env variable GITHUB_TOKEN (for hub) to not be prompt with password
    :param fork_name: name of current git name fork
    :upstream: github <user/repo_name> pattern
    """
    root = pathlib.Path()
    fork_dir = root / fork_name

    if not fork_dir.exists():
        res = c.run(f"git clone {GITHUB}/{FOG}/{fork_name}")
        with chdir(str(fork_dir)):
            c.run(f'git remote add upstream {GITHUB}/{upstream}')

    with chdir(str(fork_dir)):
        c.run('git fetch upstream')
        c.run(f'git checkout autoupdate || git checkout -b autoupdate && git pull origin autoupdate', warn=True)
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
                f'hub pull-request --base {FOG}:{FOG_BASE_BRANCH} --head {FOG}:{FOG_BASE_BRANCH} --push '
                f'-m {pr_title} -m {pr_message} --reviewer FriendsOfGalaxy --labels autoupdate --browse'
            )
        except Exception as e:
            print(e)