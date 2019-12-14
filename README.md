## galaxy-integrations-updater

Autosync FriendsOfGalaxy forks with corresponding base repo integration for GOG Galaxy 2.0.


### Setup requirements for integration

- is deployed on Github
- has release branch named `fog_release` (other rules apply only to this branch; if it doesn't exists default branch may be used)
- dependencies
    - those not installable by pip should be commited to the git repository in ready-to-use state
    - those installable by pip are stored in standard pip format in `requirements/app.txt` in the repository root (`requirements.txt` may also used)
        - dependencies are pinned (only using '==') - this is for easier security checks and building final package by us
- has valid `manifest.json` with all fields listed in Galaxy Plugin Python API documentation
    - "version" - in Semantic Versioning but without extensions like "beta" - to be comparable
    - "script" - cannot link to upper directory file

### Build process

`fog_release` branch is searched for `manifest.json` location automatically. The direct parent of `manifest.json` is treated as *source directory* and only this is copied to the final build during release package preparation.

Dependencies are installed in `dependencies_dir` (see below) using [pip's --target option](https://pip.pypa.io/en/stable/reference/pip_install/#cmdoption-t).

### Configuration

Optional config file `.fog_config.json` has to be placed in the root directory of the git repository.
Currently supported parameters:

| Name             | Default       | Description |
| -------------    |:-------------:|:-------:|
| dependencies_dir | "."           | Directory where dependencies are installed. Relative to directory where `manifest.json` is placed. |


#### Examplary .fog_config.json
```json
{
    "dependencies_dir": "third-party-modules"
}
```
