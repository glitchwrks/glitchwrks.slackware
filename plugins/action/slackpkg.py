# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Glitch Works, LLC
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from ansible.errors import AnsibleError
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.parsing.convert_bool import boolean
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display

from ansible_collections.glitchwrks.slackware.plugins.plugin_utils.slackrepo import (
    describe_source,
    load_repos,
    normalize_repo_urls,
    resolve,
)

display = Display()

RESOLVE_STATES = frozenset(('present', 'installed', 'latest'))


def _split_names(value):
    """Accept a list, a comma-separated string, or a list of comma-separated strings."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    names = []
    for item in value:
        for name in to_text(item).split(','):
            name = name.strip()
            if name and name not in names:
                names.append(name)
    return names


class ActionModule(ActionBase):

    TRANSFERS_FILES = False
    _VALID_ARGS = frozenset((
        'name', 'pkg', 'state', 'update_cache',
        'resolve_deps', 'repo_urls', 'validate_certs', 'ca_path',
    ))

    def run(self, tmp=None, task_vars=None):
        task_vars = task_vars or {}
        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp

        args = dict(self._task.args)
        if 'name' in args and 'pkg' in args:
            return dict(result, failed=True, msg="parameters are mutually exclusive: name|pkg")
        names = _split_names(args.pop('name', args.pop('pkg', None)))
        if not names:
            return dict(result, failed=True, msg="missing required arguments: name")

        resolve_deps = boolean(args.pop('resolve_deps', True), strict=False)
        repo_urls = args.pop('repo_urls', None)
        validate_certs = boolean(args.pop('validate_certs', True), strict=False)
        ca_path = args.pop('ca_path', None)
        state = args.get('state', 'present')

        packages = names
        if resolve_deps and state in RESOLVE_STATES:
            if not repo_urls:
                for var in ('slackware_repo_urls', 'slackrepo_url'):
                    if task_vars.get(var):
                        repo_urls = self._templar.template(task_vars[var])
                        break
            repo_urls = normalize_repo_urls(repo_urls)
            if repo_urls:
                try:
                    deps = load_repos(repo_urls, validate_certs=validate_certs, ca_path=ca_path)
                    packages = resolve(deps, names, describe_source(repo_urls), strict=False)
                except AnsibleError as e:
                    return dict(result, failed=True, msg="dependency resolution failed: %s" % e.message)
            else:
                display.warning("glitchwrks.slackware.slackpkg: no repo_urls and neither slackware_repo_urls "
                                "nor slackrepo_url is set; installing the packages as listed without "
                                "resolving dependencies")

        args['name'] = packages
        try:
            result.update(self._execute_module(module_name='community.general.slackpkg',
                                               module_args=args, task_vars=task_vars))
        finally:
            if not self._task.async_val:
                self._remove_tmp_path(self._connection._shell.tmpdir)

        result['packages'] = packages
        result['added_dependencies'] = [p for p in packages if p not in names]
        return result
