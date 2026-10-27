# glitchwrks.slackware

Ansible support for [Slackware Linux](http://www.slackware.com/): package installs that resolve
their own dependencies, and service management through `/etc/rc.d` scripts.

Maintained by [Glitch Works, LLC](https://www.glitchwrks.com/), where it manages a fleet of
Slackware workstations.

## Contents

| Name | Type | Description |
| --- | --- | --- |
| `glitchwrks.slackware.slackpkg` | module | Drop-in replacement for `community.general.slackpkg` that adds missing dependencies before installing |
| `glitchwrks.slackware.slackdeps` | lookup | Expands package names to their full dependency set, dependencies first |
| `glitchwrks.slackware.slackware_service` | module | Starts, stops, restarts, reloads, enables and disables `rc.d` services |

Full documentation for each is available with `ansible-doc`, for example
`ansible-doc glitchwrks.slackware.slackpkg`.

## Requirements

- ansible-core 2.19 or later on the controller
- [`community.general`](https://galaxy.ansible.com/ui/repo/published/community/general/), installed
  automatically as a dependency
- Slackware 15.0 or -current on managed hosts, with
  [slackpkg+](https://slakfinder.org/slackpkg+.html) configured for any third-party repositories

## Installation

```sh
ansible-galaxy collection install glitchwrks.slackware
```

Or straight from GitHub:

```sh
ansible-galaxy collection install git+https://github.com/glitchwrks/glitchwrks.slackware.git
```

## Dependency resolution

Slackware's package tools deliberately don't track dependencies. Repositories can still publish
them, though: a `PACKAGE REQUIRED:` line for each package in `PACKAGES.TXT` lists what it needs.
This collection reads that metadata on the controller and works out the full install set before
anything touches a host.

### Building a repository with dependency metadata

[slackrepo](https://idlemoor.github.io/slackrepo/) builds packages from SlackBuilds and records
each package's dependencies as it goes. With `gen_repos_files.sh` enabled, it publishes them in
`PACKAGES.TXT`:

```sh
# /etc/slackrepo/slackrepo_SBo.conf
USE_GENREPOS='1'
```

Serve the package repository over HTTP or HTTPS, and add it to slackpkg+ on your hosts as usual.
Some third-party repositories, such as SlackOnly, also publish `PACKAGE REQUIRED:` lines, and can
be used the same way.

### Pointing the collection at your repositories

Set `slackware_repo_urls` in your inventory, listing each repository's base URL (the directory
containing `PACKAGES.TXT`) in priority order:

```yaml
# group_vars/slackware.yml
slackware_repo_urls:
  - https://packages.example.com/15.0/x86_64/
  - https://packages.slackonly.com/pub/packages/15.0-x86_64/
```

When a package is in more than one repository, its dependencies come from the first one listed,
matching slackpkg+ repository priority. A single `slackrepo_url` string is also accepted, for
inventories that already use it. Both plugins also take the URLs directly as `repo_urls`.

### Installing packages

```yaml
- name: Install KiCad and everything it needs
  glitchwrks.slackware.slackpkg:
    name: kicad
    state: present
```

The task result includes `packages`, everything that was installed, and `added_dependencies`,
what resolution added to your list.

A few details worth knowing:

- **Existing dependency lists keep working.** Lists produced by `sqg` and pasted into playbooks
  install the same set; duplicates are dropped and anything missing is added. You can trim them
  down to top-level packages at your own pace.
- **Stock packages pass through.** Names not in any configured repository, such as packages from
  the Slackware tree itself, are installed as listed.
- **Missing dependencies fail early.** If a repository package needs something no repository
  has, the task fails on the controller before anything is installed.
- **Removal is literal.** `state: absent` removes only the packages listed, never their
  dependencies.
- **Opting out.** `resolve_deps: false` installs exactly what is listed.

`PACKAGES.TXT` is cached on the controller under `~/.ansible/cache/glitchwrks.slackware` and
revalidated with each use, so an unchanged repository isn't downloaded again for every host, and a
freshly rebuilt one is picked up right away.

### Using the lookup directly

`slackdeps` returns the same install set, for use with other modules or for inspecting what a
package would pull in:

```yaml
- name: Show KiCad's dependencies
  ansible.builtin.debug:
    msg: "{{ lookup('glitchwrks.slackware.slackdeps', 'kicad') }}"
```

## Service management

`slackware_service` drives `/etc/rc.d/rc.<name>` scripts:

```yaml
- name: Enable and start sshd
  glitchwrks.slackware.slackware_service:
    name: sshd
    enabled: true
    state: started

- name: Stop and disable NetworkManager
  glitchwrks.slackware.slackware_service:
    name: networkmanager
    pidfile: /var/run/NetworkManager/NetworkManager.pid
    state: stopped
    enabled: false
```

- **Enabling** sets the script's execute bits, which is how Slackware's boot scripts decide what
  to run. Stock scripts are already called from `rc.M` or `rc.inet2`; services added from
  SlackBuilds usually also need an entry in `rc.local` (and `rc.local_shutdown`).
- **Running state** comes from the service's PID file, `/var/run/<name>.pid` by default. A PID
  file only counts if its process is alive, so one left behind by a crash reads as stopped. Set
  `pidfile` for services that keep it elsewhere, or `pattern` to match the process command line
  for services that write none.
- **Disabled scripts can still be stopped**, because scripts are run through their `#!`
  interpreter rather than executed directly.

## Development

Tests use `ansible-test`, which expects the collection at
`ansible_collections/glitchwrks/slackware`:

```sh
mkdir -p ~/src/ansible_collections/glitchwrks
git clone https://github.com/glitchwrks/glitchwrks.slackware ~/src/ansible_collections/glitchwrks/slackware
cd ~/src/ansible_collections/glitchwrks/slackware
ansible-test sanity --docker
ansible-test units --docker
```

Issues and pull requests are welcome. For changes that affect users, add a changelog fragment
under `changelogs/fragments/`; see the
[antsibull-changelog documentation](https://ansible.readthedocs.io/projects/antsibull-changelog/changelogs/).

## License

GNU General Public License v3.0 or later. See [LICENSE](LICENSE).
