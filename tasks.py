import pathlib
import os
from invoke import task
import sys
import subprocess
import contextlib


GITHUB = 'https://github.com'
FOG = 'FriendsOfGalaxy'
FILES_TO_EXCLUDE = ['README.md', '.travis.yml']


@contextlib.contextmanager
def chdir(dirname=None):
    curdir = os.getcwd()
    try:
        if dirname is not None:
            os.chdir(dirname)
        yield
    finally:
        os.chdir(curdir)


TEST_FORK_ID = 'Bethesda'
TEST_UPSTREAM = 'TouwaStar/Galaxy_Plugin_Bethesda'

@task
def check_for_updates(c, fork_name=FORK_ID, upstream=TEST_UPSTREAM, release_branch='master'):
    """
    :param fork_name: name of current git name fork
    :upstream: github <user/repo_name> pattern
    """

    # How to featch from original fork: https://github.com/github/hub/issues/1368
    root = pathlib.Path()
    fork_dir = root / fork_name

    if not fork_dir.exists():
        c.run(f"git clone {GITHUB}/{FOG}/{fork_name}")
        with chdir(fork_dir):
            c.run(f'git remote add upstream {GITHUB}/{upstream}')

    with chdir(fork_dir):
        c.run('git fetch upstream')
        # TODO check the output to find out if there were any changes
        version = '1'  # TODO check repo version
        c.run(f'git checkout -b update_{version}')
        c.run(f'git merge --no-commit --no-ff upstream {release_branch}')
        c.run(f'git reset --hard -- {' '.join(FILES_TO_EXCLUDE)}')
        c.run(f'git merge {release_branch}')
        pr_message = f"Update to ver. {version}\n\nSyncing to the original repository new version: {version}"
        c.run(f'hub pull-request -m {pr_message}')

