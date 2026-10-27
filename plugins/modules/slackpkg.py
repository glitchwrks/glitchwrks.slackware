# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Glitch Works, LLC
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# This module is implemented as an action plugin (plugins/action/slackpkg.py),
# which resolves dependencies on the controller and then runs
# community.general.slackpkg on the host. This file holds its documentation.

from __future__ import annotations

DOCUMENTATION = r'''
module: slackpkg
short_description: Install Slackware packages with dependencies resolved from repository metadata
version_added: 0.1.0
author:
  - Jonathan Chapman (@glitchwrks)
description:
  - Wraps M(community.general.slackpkg). For O(state=present) and O(state=latest), the
    package list is first expanded on the controller using the C(PACKAGE REQUIRED:) lines
    in the repositories' C(PACKAGES.TXT), the same data the
    P(glitchwrks.slackware.slackdeps#lookup) lookup uses.
  - Lists that already include their dependencies, such as ones produced by C(sqg),
    work unchanged. Duplicates are dropped and anything missing is added.
  - Names found in none of the repositories are passed through as listed, so stock
    Slackware packages and packages from repositories without dependency metadata still
    install normally. A dependency of a repository package that is itself missing from
    every repository fails the task before anything is installed.
  - O(state=absent) never resolves dependencies; only the listed packages are removed.
  - If no repositories are configured, a warning is shown and the packages are
    installed as listed.
options:
  name:
    description:
      - Packages to install or remove. A list, a comma-separated string, or a mix.
    required: true
    type: list
    elements: str
    aliases: [pkg]
  state:
    description: Passed to M(community.general.slackpkg).
    choices: [present, absent, latest, installed, removed]
    default: present
    type: str
  update_cache:
    description: Passed to M(community.general.slackpkg).
    default: false
    type: bool
  resolve_deps:
    description: Expand O(name) with dependencies from the repositories.
    default: true
    type: bool
  repo_urls:
    description:
      - Base URLs of the repositories, each the directory containing C(PACKAGES.TXT), in
        priority order. A single URL or a comma-separated string is also accepted.
      - Defaults to the C(slackware_repo_urls) variable, then the C(slackrepo_url) variable.
    type: list
    elements: str
  validate_certs:
    description: Verify TLS certificates when fetching C(PACKAGES.TXT). Ignored for plain HTTP.
    default: true
    type: bool
  ca_path:
    description: CA bundle used to verify repository certificates.
    type: path
extends_documentation_fragment:
  - ansible.builtin.action_common_attributes
  - ansible.builtin.action_common_attributes.flow
attributes:
  action:
    support: full
  async:
    support: none
  bypass_host_loop:
    support: none
  check_mode:
    support: full
  diff_mode:
    support: none
  platform:
    support: full
    platforms: linux
requirements:
  - community.general on the controller
notes:
  - C(PACKAGES.TXT) is fetched on the controller, not the managed host, and cached
    under C(~/.ansible/cache/glitchwrks.slackware).
seealso:
  - module: community.general.slackpkg
  - plugin: glitchwrks.slackware.slackdeps
    plugin_type: lookup
'''

EXAMPLES = r'''
- name: Install KiCad and whatever it needs from the repository
  glitchwrks.slackware.slackpkg:
    name: kicad
    state: present

- name: A list produced by sqg still works; missing dependencies are added
  glitchwrks.slackware.slackpkg:
    name: spice-protocol,spice,spice-gtk,gtk-vnc,libvirt,libvirt-python,virt-manager
    state: present

- name: Resolve across a private repository and a public one, in priority order
  glitchwrks.slackware.slackpkg:
    name: qgis
    repo_urls:
      - https://repo.example.com/15.0/x86_64/
      - https://packages.slackonly.com/pub/packages/15.0-x86_64/

- name: Install exactly what is listed
  glitchwrks.slackware.slackpkg:
    name: vagrant
    resolve_deps: false
'''

RETURN = r'''
packages:
  description: Packages passed to M(community.general.slackpkg), dependencies first.
  returned: always
  type: list
  elements: str
added_dependencies:
  description: Packages added by dependency resolution that were not in O(name).
  returned: always
  type: list
  elements: str
'''
