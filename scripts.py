"""Common tasks shared between all our forks."""

import os
import sys
import json
import glob
import shlex
import errno
import shutil
import pathlib
import tempfile
import argparse
import subprocess
import urllib.request
from distutils.dir_util import copy_tree
from distutils.file_util import copy_file
from distutils.version import StrictVersion

import github

FOG = 'FriendsOfGalaxy'
FOG_EMAIL = 'FriendsOfGalaxy@gmail.com'

RELEASE_MESSAGE = "Release version {tag}\n\nVersion {tag}"
RELEASE_FILE ="current_version.json"
RELEASE_FILE_COMMIT_MESSAGE = "Updated current_version.json"
DIST_DIR = os.path.join('..', 'assets')

FOG_BASE = 'master'
FOG_PR_BRANCH = 'autoupdate'
UPSTREAM_REMOTE = '_upstream'  # '_' to avoid `hub` heuristics: https://github.com/github/hub/issues/2296
ORIGIN_REMOTE = 'origin'
PATHS_TO_EXCLUDE = ['README.md', '.github/', RELEASE_FILE]


def _run(*args, **kwargs):
    cmd = list(args)
    if len(cmd) == 1:
        cmd = shlex.split(cmd[0])
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    print('executing', cmd)
    out = subprocess.run(cmd, **kwargs)
    try:
        out.check_returncode()
    except subprocess.CalledProcessError as e:
        err_str = f'{e.output}\n{e.stderr}'
        print('><', err_str)
        raise
    else:
        print('>>', out.stdout)
    return out


class LocalRepo:
    MANIFEST = 'manifest.json'
    REQUIREMENTS = 'requirements.txt'

    def __init__(self, branch=None, check_requirements=True):
        self._manifest_dir = None
        self._manifest = None

        if branch is not None and branch != self.current_branch:
            self._checkout(branch)
        if check_requirements:
            assert self.requirements_path.exists()

    @staticmethod
    def _checkout(branch):
        try:
            _run(f'git checkout --track {ORIGIN_REMOTE}/{branch}')
        except subprocess.CalledProcessError:  # no such branch on remote
            _run(f'git checkout -b {branch}')
            _run(f'git push -u {ORIGIN_REMOTE} {branch}')

    def _localize_manifest_dir(self):
        """Search for directory where manifest.json is placed starting with cwd"""
        for root, dirs, files in os.walk('.'):
            if self.MANIFEST in files:
                return root

    def load_manifest(self):
        with open(self._manifest_dir / self.MANIFEST, 'r') as f:
            self._manifest = json.load(f)
        return self._manifest.copy()

    @property
    def current_branch(self):
        proc = _run('git rev-parse --abbrev-ref HEAD')
        return proc.stdout.strip()

    @property
    def manifest_path(self):
        return self._manifest_dir / self.MANIFEST

    @property
    def requirements_path(self):
        """Requirements file is required to be placed in root"""
        return pathlib.Path(self.REQUIREMENTS)

    @property
    def version(self):
        if self._manifest is None:
            self.load_manifest()
        return self._manifest['version']

    @property
    def manifest_dir(self):
        if self._manifest is None:
            self._manifest = pathlib.Path(self._localize_manifest_dir())
        return self._manifest_dir.resolve()


class FogRepoManager:
    """Will eventually replace CLI Hub tool"""
    FOG_RELEASE = 'fog_release'

    def __init__(self, token, fork_repo):
        self.token = token
        self.fork = github.Github(token).get_repo(fork_repo)
        self.parent = self.fork.parent
        self._release_branch = None

    @property
    def release_branch(self):
        if self._release_branch is not None:
            return self._release_branch
        try:
            return self.parent.get_branch(self.FOG_RELEASE).name
        except github.GithubException as e:
            if e.status == 404:
                return self.parent.default_branch
            raise

    @property
    def upstream_user_name(self):
        return self.parent.full_name

    def _iterate_files(self, repo, ref, dir_):
        """BFS walk through parent repo files using github API
        :dir_: str or github.ContentFile.ContentFile
        """
        if isinstance(dir_, github.ContentFile.ContentFile):
            dir_ = dir_.path

        dirs = []
        for it in repo.get_contents(dir_, ref=ref):
            if it.type == 'dir':
                dirs.append(it)
            else:
                yield it
        for d in dirs:
            yield from self._iterate_files(repo, ref, d)

    def get_parent_manifest(self):
        for it in self._iterate_files(self.parent, self.release_branch, '/'):
            if it.name == 'manifest.json':
                print(f'Found manifest.json in location: {it.path}')
                return json.loads(it.decoded_content)
        raise RuntimeError('manifest.json not found in parent repository!')

    def _get_autoupdate_pr(self):
        pulls = self.fork.get_pulls(state='open', base=FOG_BASE, head=FOG_PR_BRANCH)
        assert pulls.totalCount <= 1
        if pulls.totalCount == 0:
            return None
        return pulls[0]

    def create_or_update_pr(self, version):
        title = f"Version {version}"
        pr = self._get_autoupdate_pr()

        if pr is not None:
            print(f'updating pull-request title version to {version}')
            pr.edit(title=f'Version {version}')
        else:
            print(f'creating pull-request from version {version}')
            pr = self.fork.create_pull(
                title=title,
                body="Sync with the original repository",
                base=f'{FOG}:{FOG_BASE}',
                head=f'{FOG}:{FOG_PR_BRANCH}'
            )
            pr.set_labels(['autoupdate'])


def _remove_items(paths):
    """Silently removes files or whole dir trees."""
    print('removing paths:', paths)
    for reserved_path in paths:
        try:
            try:
                os.remove(reserved_path)
            except IsADirectoryError:
                shutil.rmtree(reserved_path)
        except OSError as e:
            if e.errno != errno.ENOENT:  # file not exists
                raise


def _fog_git_init(token, repo, upstream=None):
    origin = f'https://{FOG}:{token}@github.com/{repo}.git'

    _run(f'git config user.name {FOG}')
    _run(f'git config user.email {FOG_EMAIL}')
    _run(f'git remote set-url {ORIGIN_REMOTE} {origin}')
    if upstream is not None:
        _run(f'git remote add {UPSTREAM_REMOTE} {upstream}')


def sync(api):
    """
    Checks if there is new version (in manifest) on upstream.
    If so, synchronize upstream changes to ORIGIN_REMOTE/FOG_PR_BRANCH
    """
    _fog_git_init(api.token, api.fork.full_name, upstream=api.parent.clone_url)
    local_repo = LocalRepo(branch=FOG_PR_BRANCH, check_requirements=False)

    # for now assume manifest location on remote does not changes in time (has the same place in our local fork and upstream)
    upstream_ver = api.get_parent_manifest()['version']
    if StrictVersion(upstream_ver) <= StrictVersion(local_repo.version):
        print(f'== No new version to be sync to. Upstream: {upstream_ver}, fork on branch {local_repo.current_branch}: {local_repo.version}')
        return

    _run(f'git fetch {UPSTREAM_REMOTE}')

    print('removing reserved files')
    _remove_items(PATHS_TO_EXCLUDE)

    print(f'merging latest release from {UPSTREAM_REMOTE}/{api.release_branch}')
    _run(f'git merge --no-commit --no-ff -s recursive -Xtheirs {UPSTREAM_REMOTE}/{api.release_branch}')

    print('checkout reserved files')
    _run(f'git checkout {ORIGIN_REMOTE}/{FOG_BASE} -- {" ".join(PATHS_TO_EXCLUDE)}')

    print('commit and push')
    _run(f'git commit -m "Merge upstream"')
    _run(f'git push {ORIGIN_REMOTE} {FOG_PR_BRANCH}')

    api.create_or_update_pr(local_repo.version)


def build(output, user_repo_name):
    local_repo = LocalRepo()
    src = local_repo.manifest_dir.resolve()

    outpath = pathlib.Path(output).resolve()
    try:
        outpath.relative_to(src)
    except ValueError:
        pass
    else:
        raise RuntimeError("dist (output) cannot be part of src")

    if os.path.exists(output):
        shutil.rmtree(output)

    print(f'copy integration code ignoring {RELEASE_FILE}, tests and all hidden files')
    to_ignore = shutil.ignore_patterns(RELEASE_FILE, '.*', 'test_*.py', '*_test.py', '*.pyc')
    shutil.copytree(src, output, ignore=to_ignore)

    env = os.environ.copy()
    if sys.platform == "win32":
        pip_platform = "win32"
    elif sys.platform == "darwin":
        pip_platform = "macosx_10_12_x86_64"
        # making sure to work on macos 10.12 in case of building from sources
        env["MACOSX_DEPLOYMENT_TARGET"] = "10.12"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
        _run(f'pip-compile {local_repo.requirements_path} --output-file=-', stdout=tmp, stderr=subprocess.PIPE, capture_output=False)
        _run('pip', 'install',
            '-r', tmp.name,
            '--platform', pip_platform,
            '--target', output,
            '--python-version', '37',
            '--no-compile',
            '--no-deps',
            env=env
        )
    os.unlink(tmp.name)

    print('clean up dist directories')
    for dir_ in glob.glob(f"{output}/*.dist-info"):
        shutil.rmtree(dir_)
    for test in glob.glob(f"{output}/**/test_*.py", recursive=True):
        os.remove(test)

    print('add update_url entry in manifest')
    manifest = local_repo.load_manifest()
    manifest['update_url'] = f'https://raw.githubusercontent.com/{user_repo_name}/{FOG_BASE}/{RELEASE_FILE}'
    with open(outpath / 'manifest.json', 'w') as f:
        json.dump(manifest, f, indent=4)


def release(build_dir):
    """Zips dirs given in build_dir and upload them as github release
    build_dir should contain asset for windows and/or macos.
    Asset names should start with windows or macos (case insensitive)
    """
    asset_dirs = os.listdir(build_dir)
    print(asset_dirs)
    if not asset_dirs:
        raise RuntimeError(f'No assets found in {build_dir}')

    # Remove assets dir
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR)

    # Zip build assets
    zip_names = {'windows', 'macos'}
    for zip_name in zip_names:
        for asset_dir in asset_dirs:
            if asset_dir.lower().startswith(zip_name):
                src = os.path.join(build_dir, asset_dir)
                asset = os.path.join(DIST_DIR, zip_name)
                shutil.make_archive(asset, 'zip', root_dir=src, base_dir='.')
                break
        else:
            RuntimeError(f'No asset for {zip_name}!')

    print('Preparing assets')
    asset_cmd = []
    _, _, filenames = next(os.walk(DIST_DIR))
    for filename in filenames:
        asset_cmd.append('-a')
        asset_cmd.append(str(pathlib.Path(DIST_DIR).absolute() / filename))

    print('Creating tag and releasing on github with assets')
    with open(pathlib.Path(build_dir) / 'manifest.json', 'r') as f:
        version_tag = json.load(f)['version']
    _run('hub', 'release', 'create', version_tag,
        '-m', RELEASE_MESSAGE.format(tag=version_tag),
        *asset_cmd
    )


def update_release_file(api):
    version_tag = LocalRepo().version

    proc = _run(f'hub release show --show-downloads {version_tag}', text=True)
    lines = proc.stdout.split()
    zip_urls = [ln for ln in lines if ln.endswith('.zip')]

    assets = []
    for url in zip_urls:
        asset = {
            "browser_download_url": url,
            "name": url.split('/')[-1]
        }
        assets.append(asset)
    data = {
        "tag_name": version_tag,
        "assets": assets
    }
    with open(RELEASE_FILE, 'w') as f:
        json.dump(data, f, indent=4)

    _fog_git_init(api.token, api.fork.full_name)

    _run(f'git add {RELEASE_FILE}')
    _run(f'git commit -m "{RELEASE_FILE_COMMIT_MESSAGE}"')
    _run(f'git push {ORIGIN_REMOTE} HEAD:{FOG_BASE}')


def main():
    current_dir = pathlib.Path(os.getcwd()).name
    default_repo = f'{FOG}/{current_dir}'

    parser = argparse.ArgumentParser()
    parser.add_argument('task', choices=['sync', 'build', 'release', 'update_release_file'])
    parser.add_argument('--dir', required=sys.argv[1] in ['build', 'release'], help='build directory')
    parser.add_argument('--token', default=os.environ.get('GITHUB_TOKEN'), help='github token with repo access')
    parser.add_argument('--repo', default=default_repo, help='github_user/repository_name')

    args = parser.parse_args()
    if args.token:
        frm = FogRepoManager(args.token, args.repo)
    else:
        print('GITHUB_TOKEN not found')

    if args.task == 'sync':
        sync(frm)
    elif args.task == 'build':
        build(args.dir, args.repo)
    elif args.task == 'release':
        release(args.dir)
    elif args.task == 'update_release_file':
        update_release_file(frm)
    else:
        raise RuntimeError(f'unknown command {task}')


if __name__ == "__main__":
    main()