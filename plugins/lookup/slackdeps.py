# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Glitch Works, LLC
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

DOCUMENTATION = r'''
name: slackdeps
short_description: Expand Slackware packages to their full dependency set
version_added: 0.1.0
author:
  - Jonathan Chapman (@glitchwrks)
description:
  - Fetches C(PACKAGES.TXT) from one or more Slackware package repositories over HTTP or
    HTTPS and expands the given package names into the complete set of packages to
    install, using the C(PACKAGE REQUIRED:) field. Repositories built by slackrepo with
    C(gen_repos_files.sh) publish this field, as do some third-party repositories.
  - Dependencies are returned before the packages that need them.
  - Resolution happens on the controller. A package or dependency found in none of the
    repositories fails the lookup before any host is changed.
  - Repositories are searched in the order given. A package present in more than one
    takes its dependencies from the first, matching slackpkg+ repository priority.
  - Version constraints such as C(pkg >= 1.2-x86_64-1) are ignored. Alternatives
    written C(a|b) resolve to the first one present in the repositories.
  - C(PACKAGES.TXT) is cached under C(~/.ansible/cache/glitchwrks.slackware) on the
    controller and revalidated with a conditional GET on each use, so an unchanged
    repository is not downloaded again and a rebuilt one is picked up immediately.
options:
  _terms:
    description: Package names (base names, no version).
    required: true
  repo_urls:
    description:
      - Base URLs of the repositories, each the directory containing C(PACKAGES.TXT),
        in priority order. A single URL or a comma-separated string is also accepted.
      - If both variables are set, O(repo_urls) comes from C(slackware_repo_urls).
    type: list
    elements: str
    required: true
    vars:
      - name: slackrepo_url
      - name: slackware_repo_urls
  validate_certs:
    description: Verify TLS certificates. Ignored for plain HTTP.
    type: boolean
    default: true
  ca_path:
    description: CA bundle used to verify repository certificates.
    type: path
seealso:
  - module: glitchwrks.slackware.slackpkg
'''

EXAMPLES = r'''
- name: Install role packages with their dependencies
  community.general.slackpkg:
    name: "{{ lookup('glitchwrks.slackware.slackdeps', *top_level_pkgs) }}"
    state: present

- name: Show what installing KiCad would pull in from two repositories
  ansible.builtin.debug:
    msg: "{{ lookup('glitchwrks.slackware.slackdeps', 'kicad',
             repo_urls=['https://repo.example.com/15.0/x86_64/',
                        'https://packages.slackonly.com/pub/packages/15.0-x86_64/']) }}"
'''

RETURN = r'''
_raw:
  description: Package names to install, dependencies first.
  type: list
  elements: str
'''

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase

from ansible_collections.glitchwrks.slackware.plugins.plugin_utils.slackrepo import (
    describe_source,
    load_repos,
    normalize_repo_urls,
    resolve,
)


class LookupModule(LookupBase):

    def run(self, terms, variables=None, **kwargs):
        self.set_options(var_options=variables, direct=kwargs)
        repo_urls = normalize_repo_urls(self.get_option('repo_urls'))
        if not repo_urls:
            raise AnsibleError("slackdeps: no repositories; set repo_urls or slackware_repo_urls")
        try:
            deps = load_repos(repo_urls,
                              validate_certs=self.get_option('validate_certs'),
                              ca_path=self.get_option('ca_path'))
            return [resolve(deps, terms, describe_source(repo_urls), strict=True)]
        except AnsibleError as e:
            raise AnsibleError("slackdeps: %s" % e.message)
