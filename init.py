import os
import argparse
import json
import sys
import pathlib

import github

from scripts import FogRepoManager, FOG, FOG_EMAIL
from context import UserRepoContext
from update_templates import copy_workflows, dump_readme


def edit_metadata(man: FogRepoManager):
    """
    Normalize name and edits metadata of our fork (description, url, disabling issues...)
    """
    print(f'== Looking for {man.parent.full_name} manifest file...')
    manifest = man.get_parent_manifest()
    name = 'galaxy-integration-' + manifest['platform']
    description = "In case of any issues please refer to the original repository:"
    homepage = man.fork.parent.html_url
    print('== editing repo metadata:', name, description, homepage)
    man.fork.edit(name, description, homepage, has_issues=False, allow_squash_merge=False)


def purge_content(man: FogRepoManager):
    """
    Remove all content and create first commit with our files.
    Allows standard synchronization flow for the first time.
    """
    print('== deleting releases thorugh api')
    for rel in man.fork.get_releases():
        rel.delete_release()

    print('== initialize new github repo and force push with only our template files')
    with UserRepoContext(man.token, FOG, FOG_EMAIL, man.fork.name, clone=False) as c:
        copy_workflows(repo_dir=c.cwd)
        dump_readme(repo_dir=c.cwd, title=man.fork.name, url=man.parent.html_url)
        c.run(f'git add .')
        c.run(f'git commit -m "Reset repository"')
        c.run(f'git push -u --force origin master')

        print('== deleting all branches except default branch')
        for branch in man.fork.get_branches():
            if branch.name == man.fork.default_branch:
                continue
            c.run(f'git push github --delete {branch.name}')

        print('== deleting tags')
        for tag in man.fork.get_tags():
            c.run(f'git push origin :refs/tags/{tag.name}')


def fork_repo(token: str, repo_name: str) -> github.Repository.Repository:
    """
    Forks repository if not already forked. Returns our fork.
    """
    g = github.Github(token)
    fog_user = g.get_user()

    original_repo = g.get_repo(repo_name)
    for fork in original_repo.get_forks():
        if fork.owner.login == fog_user.login:
            break
    else:
        print(f'{repo_name} is not forked yet. Let us fork!')
        fork = fog_user.create_fork(original_repo)
    return fork


def add_to_synced(fork_name: str):
    """
    Adds FoG fork repo to config.json
    """
    SYNC_CONFIG_PATH = os.path.join('config.json')
    with open(SYNC_CONFIG_PATH, 'r+') as f:
        config = json.load(f)
        if fork_name in config['forks_to_sync']:
            print('Already in sync config')
            return
        config['forks_to_sync'].append(fork_name)
        f.seek(0)
        json.dump(config, f, indent=4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('repo', help="Original repository full name for example user/galaxy-plugin-xxx")
    parser.add_argument('--purge', action='store_true', help="delete all files and commit. Used after initial fork")

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(0)
    args = parser.parse_args()

    try:
        token = os.environ['FOG_GITHUB_TOKEN']
    except KeyError:
        print('FOG_GITHUB_TOKEN required as environmental variable')

    fork = fork_repo(token, args.repo)
    man = FogRepoManager(token, fork.full_name)
    edit_metadata(man)
    add_to_synced(fork.name)
    if args.purge:
        msg = 'Unreversable decision. Are you sure you want to remove all the content, all branches and releases from this repository?'
        if input(f"{msg} (y/N)? ").lower() == 'y':
            purge_content(man)
