"""Script for updating github workflows for all our integration forks that have to be synchronized with original repository"""

import os
import json
import subprocess
import shutil
import shlex
import glob


class GitUserContext:
    def __init__(self, token, user, email):
        self.token = token
        self.user = user
        self.email = email
        self._run(f'git config --global user.email "{self.email}"')
        self._run(f'git config --global user.name "{self.user}Bot"')

    def _run(self, cmd: str, **kwargs):
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.STDOUT)
        kwargs.setdefault("text", True)
        cmd = shlex.split(cmd)
        print('-- executing', cmd)
        proc = subprocess.run(cmd, **kwargs)
        print(proc.stdout)
        proc.check_returncode()

    def clone_repo(self, repo):
        self._run(f'git clone https://{self.user}:{self.token}@github.com/{self.user}/{repo}.git')

    def update_workflows(self, repo):
        print('> copying workflow files')
        target = os.path.join(repo, '.github', 'workflows')
        for file_ in glob.glob(r'templates/.github/workflows/*.yml'):
            shutil.copy(file_, target)
        self._run(f'git commit -a -m "Workflows autoupdate"', cwd=repo)
        self._run(f'git push origin master', cwd=repo)


if __name__ == "__main__":
    with open('config.json', 'r') as f:
        names = json.load(f)['forks_to_sync']

    tkn = os.environ['GITHUB_TOKEN']
    fog = GitUserContext(tkn, 'FriendsOfGalaxy', 'FriendsOfGalaxy@gmail.com')
    for repo_name in names:
        fog.clone_repo(repo_name)
        fog.update_workflows(repo_name)
