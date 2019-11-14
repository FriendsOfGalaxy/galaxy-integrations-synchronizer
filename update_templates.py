"""Script for updating github workflows for all our integration forks that have to be synchronized with original repository"""

import os
import json
import subprocess
import shutil
import glob

from context import UserRepoContext
from scripts import FogRepoManager, BOT_USER, FOG_USER


def dump_readme(repo_dir, man: FogRepoManager):
    title = man.fork.name
    url = man.parent.html_url
    license_type = man.get_parent_license().key
    if license_type == 'mit':
        cp = ''
    else:
        owner = man.parent.owner
        cp = f'Copyright {man.parent.created_at.year} [{owner.name or owner.login}]({owner.html_url})'

    with open(os.path.join('templates', 'README.md'), 'r') as f:
        readme = f.read().format(title=title, url=url, copyright=cp)
        with open(os.path.join(repo_dir, 'README.md'), 'w') as g:
            g.write(readme)


def copy_workflows(repo_dir):
    target = os.path.join(repo_dir, '.github', 'workflows')
    os.makedirs(target, exist_ok=True)
    for file_ in glob.glob(r'templates/.github/workflows/*.yml'):
        shutil.copy(file_, target)


if __name__ == "__main__":

    with open('config.json', 'r') as f:
        names = json.load(f)['forks_to_sync']

    tkn = os.environ['GITHUB_TOKEN']
    proc = subprocess.run(['git', 'show', '-s', '--format=%B', 'HEAD'], text=True, capture_output=True)
    last_commit_msg = proc.stdout.strip()

    for repo_name in names:
        man = FogRepoManager(tkn, f'{FOG_USER.login}/{repo_name}')

        with UserRepoContext(tkn, FOG_USER.login, BOT_USER.login, BOT_USER.email, repo_name) as c:
            print('> copying workflow files')
            copy_workflows(repo_dir=c.cwd)
            dump_readme(repo_dir=c.cwd, man=man)
            c.run(f'git commit -a -m "{last_commit_msg}"')
            c.run(f'git push origin master')
