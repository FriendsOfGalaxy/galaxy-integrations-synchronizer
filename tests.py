"""Common tests shared between all our forks.
They are run versus build_directory specified as TARGET environmental variable
"""

import os
import sys
import json
import pytest
import logging
import subprocess
from distutils.version import StrictVersion


@pytest.fixture()
def manifest():
    target_dir = os.environ['TARGET']
    with open(target_dir + '/manifest.json', 'r') as f:
        manifest = json.load(f)
    return manifest


def test_manifest_elements(manifest):
    for i in ["name", "platform", "guid", "version", "description", "author", "email", "url", "script", "update_url"]:
        assert i in manifest


def test_manifest_version_versus_master_branch(manifest, capsys):
    """Galaxy downloads plugins only if the version is higher than in local copy.
    Check if new version will be bumped using StrictVersion comparison
    """
    proc = subprocess.run(
        ["git", "show", "origin/master:current_version.json"],
        check=False,
        text=True,
        capture_output=True
    )
    if proc.returncode != 0:
        with capsys.disabled():
            print(f"\nLooks like this is the first remote version of this fork: {proc.stderr}")
        return
    prev_ver = json.loads(proc.stdout)['tag_name']

    assert StrictVersion(manifest['version']) > StrictVersion(prev_ver)
