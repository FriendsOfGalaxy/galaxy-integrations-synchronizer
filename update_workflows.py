"""Script for updating github workflows for all our integration forks that have to be synchronized with original repository"""

import os
import json
import subprocess
import shutil
import glob


class GitUserContext:
    def __init__(self, token, user):
        self.token = token
        self.user = user

    def clone_repo(self, repo):
        subprocess.run(['git', 'clone', f'https://{self.user}:{self.token}@github.com/{self.user}/{repo}.git'])

    def update_workflows(self, repo):
        target = os.path.join(repo, '.github', 'workflows')
        for file_ in glob.glob(r'templates/.github/workflows/*.yml'):
            shutil.copy(file_, target)
        subprocess.run(['git', 'commit', '-a', '-m', "Workflows autoupdate"], cwd=repo)
        subprocess.run(['git', 'push', 'origin', 'master'], cwd=repo)


if __name__ == "__main__":
    with open('config.json', 'r') as f:
        names = json.load(f)['forks_to_sync']

    tkn = os.environ['GITHUB_TOKEN']
    fog = GitUserContext(tkn, "FriendsOfGalaxy")
    for repo_name in names:
        fog.clone_repo(repo_name)
        fog.update_workflows(repo_name)
