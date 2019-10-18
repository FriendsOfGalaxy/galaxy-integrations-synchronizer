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
import subprocess
import urllib.request
from distutils.dir_util import copy_tree
from distutils.file_util import copy_file
from distutils.version import StrictVersion

FOG_DIR = '.fog/'
sys.path.insert(0, FOG_DIR)
import config


_ENV_TOKEN = os.environ['GITHUB_TOKEN']
_ENV_REPOSITORY = os.environ['REPOSITORY']

GITHUB = 'https://github.com'

def _localize_manifest_dir():
    """Search for directory where manifest.json is placed starting with cwd"""
    for root, dirs, files in os.walk('.'):
        if 'manifest.json' in files:
            return root

MANIFEST_DIR = _localize_manifest_dir()
MANIFEST_LOCATION = os.path.join(MANIFEST_DIR, 'manifest.json')

REQUIREMENTS_PATH = 'requirements.txt'

if config.UPSTREAM.startswith(GITHUB):
    UPSTREAM_USER_REPO = config.UPSTREAM.split('/', 3)[-1]
else:
    raise NotImplementedError(f'UPSTREAM does not starts with {GITHUB}. Other services not supported')

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
        err_str = f'{e.output}\n{e.stderr}'
        print('><', err_str)
        raise
    else:
        print('>>', out.stdout)
    return out


def _load_version():
    with open(MANIFEST_LOCATION, 'r') as f:
        return json.load(f)['version']


def _load_upstream_version():
    url = f'https://raw.githubusercontent.com/{UPSTREAM_USER_REPO}/{config.RELEASE_BRANCH}/{MANIFEST_LOCATION}'
    resp = urllib.request.urlopen(url)
    upstream_manifest = json.loads(resp.read().decode('utf-8'))
    return upstream_manifest['version']


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


def build(output):
    src = pathlib.Path(MANIFEST_DIR).resolve()
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
        _run(f'pip-compile {REQUIREMENTS_PATH} --output-file=-', stdout=tmp, stderr=subprocess.PIPE, capture_output=False)
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
    with open(src / 'manifest.json', 'r') as f:
        manifest = json.load(f)
    manifest['update_url'] = UPDATE_URL
    with open(output + '/manifest.json', 'w') as f:
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

    # Prepare assets
    asset_cmd = []
    _, _, filenames = next(os.walk(DIST_DIR))
    for filename in filenames:
        asset_cmd.append('-a')
        asset_cmd.append(str(pathlib.Path(DIST_DIR).absolute() / filename))

    # Create and upload github tag and release with assets
    version_tag = _load_version()
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
        build_dir = sys.argv[2]
        release(build_dir)
    elif task == 'update_release_file':
        update_release_file()
    elif task == 'sync':
        sync()
    elif task == 'build':
        build_dir = sys.argv[2]
        build(build_dir)
    else:
        raise RuntimeError(f'unknown command {task}')
