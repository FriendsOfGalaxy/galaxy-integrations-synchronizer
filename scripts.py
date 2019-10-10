"""Common tasks shared between all our forks."""

import os
import sys
import json
import shlex
import errno
import shutil
import pathlib
import subprocess
import urllib.request
from distutils.version import StrictVersion

FOG_DIR = '.fog'
sys.path.insert(0, FOG_DIR)
import config


_ENV_TOKEN = os.environ['GITHUB_TOKEN']
_ENV_REPOSITORY = os.environ['REPOSITORY']

GITHUB = 'https://github.com'
MANIFEST_LOCATION = os.path.join(config.SRC, 'manifest.json')

if config.UPSTREAM.startswith(GITHUB):
    UPSTREAM_USER_REPO = config.UPSTREAM.split('/', 3)[-1]
else:
    raise NotImplementedError(f'UPSTREAM does not starts with {GITHUB}. Other services not supported')

FOG = 'FriendsOfGalaxy'
FOG_EMAIL = 'FriendsOfGalaxy@gmail.com'

RELEASE_MESSAGE = "Release version {tag}\n\nVersion {tag}"
RELEASE_FILE ="current_version.json"
RELEASE_FILE_COMMIT_MESSAGE = "Updated current_version.json"
BUILD_DIR = os.path.join('..', 'assets')
RELEASE_INFO_FILE = os.path.join('..', 'release_info')

FOG_BASE = 'master'
FOG_PR_BRANCH = 'autoupdate'
UPSTREAM_REMOTE = '_upstream'  # '_' to avoid `hub` heuristics: https://github.com/github/hub/issues/2296
ORIGIN_REMOTE = 'origin'
UPDATE_URL = f'https://raw.githubusercontent.com/{_ENV_REPOSITORY}/{FOG_BASE}/{RELEASE_FILE}'
PATHS_TO_EXCLUDE = ['README.md', '.github/', FOG_DIR, RELEASE_FILE]


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
        err_str = e.output + '\n' + e.stderr
        print('><', err_str)
        raise
    else:
        print('>>', out.stdout)
    return out


def _remove_items(paths):
    """Silently removes files or whole dir trees"""
    _run('pwd')
    print('paths to remove:', paths)
    for reserved_path in paths:
        try:
            try:
                os.remove(reserved_path)
            except IsADirectoryError:
                shutil.rmtree(reserved_path)
        except OSError as e:
            if e.errno != errno.ENOENT:  # file not exists
                raise


def _load_version():
    with open(MANIFEST_LOCATION, 'r') as f:
        return json.load(f)['version']


def _load_upstream_version():
    url = f'https://raw.githubusercontent.com/{UPSTREAM_USER_REPO}/{config.RELEASE_BRANCH}/{MANIFEST_LOCATION}'
    resp = urllib.request.urlopen(url)
    upstream_manifest = json.loads(resp.read().decode('utf-8'))
    return upstream_manifest['version']


def _fog_git_init(upstream=None):
    origin = f'https://{FOG}:{_ENV_TOKEN}@github.com/{_ENV_REPOSITORY}.git'

    _run(f'git config user.name {FOG}')
    _run(f'git config user.email {FOG_EMAIL}')
    _run(f'git remote set-url {ORIGIN_REMOTE} {origin}')
    if upstream is not None:
        _run(f'git remote add {UPSTREAM_REMOTE} {upstream}')


def _is_pr_open():
    url = f"https://api.github.com/repos/{_ENV_REPOSITORY}/pulls?base={FOG_BASE}&head={FOG}:{FOG_PR_BRANCH}&state=open"
    resp = urllib.request.urlopen(url)
    prs = json.loads(resp.read().decode('utf-8'))
    if len(prs):
        return True
    return False


def _create_pr():
    version = _load_version()
    print('preparing pull-request for version', version)
    pr_title = f"Version {version}"
    pr_message = "Sync with the original repository"
    _run(
        f'hub pull-request --base {FOG}:{FOG_BASE} --head {FOG}:{FOG_PR_BRANCH} '
        f'-m "{pr_title}" -m "{pr_message}" --labels autoupdate'
    )


def _sync_pr():
    """ Synchronize upstream changes to ORIGIN_REMOTE/FOG_PR_BRANCH
    """
    _run(f'git fetch {UPSTREAM_REMOTE}')

    try:
        _run(f'git checkout -b {FOG_PR_BRANCH} --track {ORIGIN_REMOTE}/{FOG_PR_BRANCH}')
    except subprocess.CalledProcessError:  # no such branch on remote
        _run(f'git checkout -b {FOG_PR_BRANCH}')
        _run(f'git push -u {ORIGIN_REMOTE} {FOG_PR_BRANCH}')

    print('removing reserved files')
    _remove_items(PATHS_TO_EXCLUDE)

    print(f'merging latest release from {UPSTREAM_REMOTE}/{config.RELEASE_BRANCH}')
    _run(f'git merge --no-commit --no-ff -s recursive -Xtheirs {UPSTREAM_REMOTE}/{config.RELEASE_BRANCH}')

    print('checkout reserved files')
    _run(f'git checkout {ORIGIN_REMOTE}/{FOG_BASE} -- {" ".join(PATHS_TO_EXCLUDE)}')

    _run(f'git commit -m "Merge upstream"')
    _run(f'git push {ORIGIN_REMOTE} {FOG_PR_BRANCH}')


def sync():
    """Started from master branch"""
    _fog_git_init(config.UPSTREAM)

    pr_branch_version = _load_version()
    upstream_version = _load_upstream_version()
    if StrictVersion(upstream_version) <= StrictVersion(pr_branch_version):
        raise RuntimeError(
            '====== No new version to be sync to. ' \
            f'Upstream: {upstream_version}, fork {FOG_PR_BRANCH}: {pr_branch_version} ====='
        )

    _sync_pr()
    if _is_pr_open():
        print('creating PR skipped, as it already exists')
    else:
        _create_pr()


def _simple_archiver(output):
    """Generate zip assests in output path."""
    if os.path.exists(output):
        shutil.rmtree(output)
    os.makedirs(output)

    zip_names = ['windows', 'macos']
    for zip_name in zip_names:
        asset = os.path.join(output, zip_name)
        shutil.make_archive(asset, 'zip', root_dir=config.SRC, base_dir='.')


def release():
    # Add update_url in manifest
    with open(MANIFEST_LOCATION, 'r') as f:
        manifest = json.load(f)
    manifest['update_url'] = UPDATE_URL
    with open(MANIFEST_LOCATION, 'w') as f:
        json.dump(manifest, f, indent=4)

    # remove reserved files (beside FOG_DIR and README.md)
    paths_to_remove = set(PATHS_TO_EXCLUDE) - {FOG_DIR, 'README.md'}
    _remove_items(paths_to_remove)

    # Run pack job
    version_tag = manifest['version']
    try:
        packager = config.pack
    except AttributeError:
        packager = _simple_archiver
    packager(BUILD_DIR)

    # Prepare assets
    asset_cmd = []
    _, _, filenames = next(os.walk(BUILD_DIR))
    for filename in filenames:
        asset_cmd.append('-a')
        asset_cmd.append(str(pathlib.Path(BUILD_DIR).absolute() / filename))

    # Create and upload github tag and release with assets
    _run('hub', 'release', 'create', version_tag,
        '-m', RELEASE_MESSAGE.format(tag=version_tag),
        *asset_cmd
    )

def update_release_file():
    version_tag = _load_version()

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

    _fog_git_init()

    _run(f'git add {RELEASE_FILE}')
    _run(f'git commit -m "{RELEASE_FILE_COMMIT_MESSAGE}"')
    _run(f'git push {ORIGIN_REMOTE} HEAD:{FOG_BASE}')


if __name__ == "__main__":
    task = sys.argv[1]

    if task == 'release':
        release()
    elif task == 'update_release_file':
        update_release_file()
    elif task == 'sync':
        sync()
    else:
        raise RuntimeError(f'unknown command {task}')
