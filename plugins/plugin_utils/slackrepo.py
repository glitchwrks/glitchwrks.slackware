# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Glitch Works, LLC
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read dependency metadata from Slackware package repositories.

Shared by the glitchwrks.slackware.slackdeps lookup and the
glitchwrks.slackware.slackpkg action. Everything here runs on the controller.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from urllib.error import HTTPError

from ansible.errors import AnsibleError
from ansible.module_utils.common.text.converters import to_bytes, to_text
from ansible.module_utils.urls import open_url

CACHE_DIR = os.path.expanduser('~/.ansible/cache/glitchwrks.slackware/packages_txt')

_MEMO = {}


def normalize_repo_urls(value):
    """Accept a URL string, a comma-separated string, or a list; return a list of URLs."""
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    urls = []
    for item in value:
        for url in to_text(item).split(','):
            url = url.strip()
            if url and url not in urls:
                urls.append(url)
    return urls


def packages_txt_url(repo_url):
    return repo_url.rstrip('/') + '/PACKAGES.TXT'


def _base_name(pkgfile):
    # foo-bar-1.2-x86_64-1_tag.txz -> foo-bar
    return pkgfile.strip().rsplit('-', 3)[0]


def parse_packages_txt(text):
    """Return {package: [[alternative, ...], ...]} from PACKAGES.TXT content.

    Each package maps to its requirements; each requirement is a list of
    acceptable alternatives, in order. Version constraints are dropped.
    """
    deps, name = {}, None
    for line in text.splitlines():
        if line.startswith('PACKAGE NAME:'):
            name = _base_name(line.split(':', 1)[1])
            deps.setdefault(name, [])
        elif line.startswith('PACKAGE REQUIRED:') and name:
            for item in line.split(':', 1)[1].split(','):
                alts = [re.split(r'\s*[<>=]', a.strip())[0] for a in item.split('|')]
                alts = [a for a in alts if a]
                if alts:
                    deps[name].append(alts)
    return deps


def merge_repos(repos):
    """Merge parsed repositories, given in priority order.

    A package in more than one repository takes its dependencies from the first
    one, matching how slackpkg+ picks a package by repository priority.
    """
    merged = {}
    for deps in repos:
        for name, reqs in deps.items():
            merged.setdefault(name, reqs)
    return merged


def _write_atomic(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def fetch_packages_txt(repo_url, validate_certs=True, ca_path=None):
    """Return parsed dependency data for one repository.

    Ansible runs each task for each host in a separate worker process, so an
    in-memory cache alone would refetch PACKAGES.TXT for every host. The file is
    cached on disk instead and revalidated with a conditional GET, so an unchanged
    repository costs one small 304 response per use and a rebuilt repository is
    picked up immediately.
    """
    url = packages_txt_url(repo_url)
    if url in _MEMO:
        return _MEMO[url]

    key = hashlib.sha256(to_bytes(url)).hexdigest()
    body_path = os.path.join(CACHE_DIR, key + '.txt')
    meta_path = os.path.join(CACHE_DIR, key + '.json')

    meta = {}
    if os.path.exists(body_path):
        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except (OSError, ValueError):
            meta = {}

    headers = {}
    if meta.get('etag'):
        headers['If-None-Match'] = meta['etag']
    if meta.get('last_modified'):
        headers['If-Modified-Since'] = meta['last_modified']

    body = None
    try:
        resp = open_url(url, headers=headers, validate_certs=validate_certs, ca_path=ca_path)
        body = resp.read()
        new_meta = {
            'url': url,
            'etag': resp.headers.get('ETag'),
            'last_modified': resp.headers.get('Last-Modified'),
        }
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            _write_atomic(body_path, body)
            _write_atomic(meta_path, to_bytes(json.dumps(new_meta)))
        except OSError:
            pass  # caching is best-effort
    except HTTPError as e:
        if e.code != 304:
            raise AnsibleError("fetching %s: %s" % (url, to_text(e)))
    except Exception as e:
        raise AnsibleError("fetching %s: %s" % (url, to_text(e)))

    if body is None:
        try:
            with open(body_path, 'rb') as f:
                body = f.read()
        except OSError as e:
            raise AnsibleError("fetching %s: server returned 304 but the cached copy is unreadable: %s"
                               % (url, to_text(e)))

    _MEMO[url] = parse_packages_txt(to_text(body, errors='surrogate_or_replace'))
    return _MEMO[url]


def load_repos(repo_urls, validate_certs=True, ca_path=None):
    """Fetch and merge several repositories, given in priority order."""
    return merge_repos(fetch_packages_txt(u, validate_certs=validate_certs, ca_path=ca_path)
                       for u in repo_urls)


def describe_source(repo_urls):
    if len(repo_urls) == 1:
        return packages_txt_url(repo_urls[0])
    return 'any of %s' % ', '.join(packages_txt_url(u) for u in repo_urls)


def resolve(deps, terms, source, strict=True):
    """Expand terms to the full install set, dependencies first.

    With strict=False, top-level terms that are in none of the repositories are
    passed through unchanged in their original position (for example stock
    Slackware packages). Dependencies of packages that are in a repository must
    always resolve.
    """
    order, seen = [], set()

    def add(pkg):
        if pkg not in seen:
            seen.add(pkg)
            order.append(pkg)

    def visit(pkg, stack):
        if pkg in seen:
            return
        if pkg in stack:
            raise AnsibleError("dependency cycle: %s" % ' -> '.join(stack + (pkg,)))
        for alts in deps[pkg]:
            pick = next((a for a in alts if a in deps), None)
            if pick is None:
                if len(alts) == 1:
                    raise AnsibleError("%s (needed by %s) not in %s" % (alts[0], pkg, source))
                raise AnsibleError("%s needs one of %s, none in %s" % (pkg, '|'.join(alts), source))
            visit(pick, stack + (pkg,))
        add(pkg)

    for term in terms:
        if term in deps:
            visit(term, ())
        elif strict:
            raise AnsibleError("%s not in %s" % (term, source))
        else:
            add(term)
    return order
