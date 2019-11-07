import os
import stat
import subprocess
import shlex
import tempfile
import shutil


class UserRepoContext:
    def __init__(self, token, user, email, repo_name, clone=True):
        self.token = token
        self.user = user
        self.email = email
        self.repo = repo_name
        self.clone = clone
        self._tmpdir = None
        self._cwd = None

    @property
    def cwd(self):
        return self._cwd

    def __enter__(self):
        self._tmpdir = tempfile.mkdtemp()
        self._cwd = self._tmpdir
        auth_url = f'https://{self.user}:{self.token}@github.com/{self.user}/{self.repo}.git'

        if self.clone:
            self.run(f'git clone {auth_url}')
            self._cwd = os.path.join(self._tmpdir, self.repo)
        else:
            self.run(f'git init')
            self.run(f'git remote add origin {auth_url}')

        self.run(f'git config --local user.email "{self.email}"')
        self.run(f'git config --local user.name "{self.user}"')
        return self

    def __exit__(self, exc_type, exc_value, tb):
        def del_ro(action, name, exc):
            """Remove .git read-only files"""
            os.chmod(name, stat.S_IWRITE)
            os.remove(name)
        shutil.rmtree(self._tmpdir, onerror=del_ro)

    def run(self, cmd: str, **kwargs):
        cmd_ = shlex.split(cmd)
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.STDOUT)
        kwargs.setdefault("text", True)
        kwargs.setdefault("cwd", self._cwd)
        print(f'-- executing {cmd_}, cwd={kwargs["cwd"]}')
        proc = subprocess.run(cmd_, **kwargs)
        print(proc.stdout)
        proc.check_returncode()
        return proc
