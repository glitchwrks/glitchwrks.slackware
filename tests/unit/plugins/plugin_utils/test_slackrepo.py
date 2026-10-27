# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Glitch Works, LLC
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import io
from urllib.error import HTTPError

import pytest

from ansible.errors import AnsibleError

from ansible_collections.glitchwrks.slackware.plugins.plugin_utils import slackrepo
from ansible_collections.glitchwrks.slackware.plugins.plugin_utils.slackrepo import (
    describe_source,
    merge_repos,
    normalize_repo_urls,
    parse_packages_txt,
    resolve,
)

PACKAGES_TXT = """\
PACKAGES.TXT;  Tue Oct 27 2026

PACKAGE NAME:  qgis-3.28-x86_64-1_gw.txz
PACKAGE LOCATION:  ./academic/qgis
PACKAGE REQUIRED:  gdal,proj,libspatialite >= 5.0-x86_64-1
PACKAGE DESCRIPTION:

PACKAGE NAME:  gdal-3.6-x86_64-1_gw.txz
PACKAGE REQUIRED:  proj
PACKAGE DESCRIPTION:

PACKAGE NAME:  proj-9.1-x86_64-1_gw.txz
PACKAGE REQUIRED:
PACKAGE DESCRIPTION:

PACKAGE NAME:  libspatialite-5.0-x86_64-1_gw.txz
PACKAGE REQUIRED:  proj,missing-alt|proj
PACKAGE DESCRIPTION:

PACKAGE NAME:  python3-setuptools-rust-opt-1.5-x86_64-1_gw.txz
PACKAGE DESCRIPTION:

PACKAGE NAME:  broken-1.0-x86_64-1_gw.txz
PACKAGE REQUIRED:  nothere
PACKAGE DESCRIPTION:
"""

SRC = 'repo'


@pytest.fixture
def deps():
    return parse_packages_txt(PACKAGES_TXT)


def test_parse_names_and_requirements(deps):
    assert deps['qgis'] == [['gdal'], ['proj'], ['libspatialite']]
    assert deps['proj'] == []
    assert deps['libspatialite'] == [['proj'], ['missing-alt', 'proj']]


def test_parse_hyphenated_name_without_required_line(deps):
    assert deps['python3-setuptools-rust-opt'] == []


def test_resolve_orders_dependencies_first(deps):
    assert resolve(deps, ['qgis'], SRC) == ['proj', 'gdal', 'libspatialite', 'qgis']


def test_resolve_pasted_list_is_deduplicated(deps):
    assert resolve(deps, ['proj', 'gdal', 'qgis', 'libspatialite', 'proj'], SRC) == \
        ['proj', 'gdal', 'libspatialite', 'qgis']


def test_resolve_alternative_picks_first_available(deps):
    assert resolve(deps, ['libspatialite'], SRC) == ['proj', 'libspatialite']


def test_resolve_strict_rejects_unknown_package(deps):
    with pytest.raises(AnsibleError, match='sshpass not in repo'):
        resolve(deps, ['sshpass'], SRC)


def test_resolve_lenient_passes_unknown_through_in_place(deps):
    assert resolve(deps, ['sshpass', 'gdal'], SRC, strict=False) == ['sshpass', 'proj', 'gdal']


def test_resolve_missing_dependency_fails_even_when_lenient(deps):
    with pytest.raises(AnsibleError, match=r'nothere \(needed by broken\)'):
        resolve(deps, ['broken'], SRC, strict=False)


def test_resolve_missing_alternatives_reported():
    deps = {'a': [['x', 'y']]}
    with pytest.raises(AnsibleError, match=r'a needs one of x\|y'):
        resolve(deps, ['a'], SRC)


def test_resolve_detects_cycle():
    deps = {'a': [['b']], 'b': [['a']]}
    with pytest.raises(AnsibleError, match='cycle: a -> b -> a'):
        resolve(deps, ['a'], SRC)


def test_merge_repos_first_repository_wins():
    first = {'kicad': [['wxWidgets']], 'wxWidgets': []}
    second = {'kicad': [['other']], 'extra': []}
    assert merge_repos([first, second]) == {'kicad': [['wxWidgets']], 'wxWidgets': [], 'extra': []}


@pytest.mark.parametrize('value, expected', [
    (None, []),
    ('', []),
    ('http://a/', ['http://a/']),
    ('http://a/, http://b/', ['http://a/', 'http://b/']),
    (['http://a/', 'http://b/,http://a/'], ['http://a/', 'http://b/']),
])
def test_normalize_repo_urls(value, expected):
    assert normalize_repo_urls(value) == expected


def test_describe_source():
    assert describe_source(['http://a']) == 'http://a/PACKAGES.TXT'
    assert describe_source(['http://a/', 'http://b']) == 'any of http://a/PACKAGES.TXT, http://b/PACKAGES.TXT'


class FakeResponse:
    def __init__(self, body, headers):
        self._body = body
        self.headers = headers

    def read(self):
        return self._body


def test_fetch_caches_and_revalidates(tmp_path, monkeypatch):
    monkeypatch.setattr(slackrepo, 'CACHE_DIR', str(tmp_path))
    monkeypatch.setattr(slackrepo, '_MEMO', {})
    calls = []

    def first(url, headers=None, **kwargs):
        calls.append(dict(headers))
        return FakeResponse(PACKAGES_TXT.encode(), {'ETag': '"v1"', 'Last-Modified': 'Tue, 27 Oct 2026 12:00:00 GMT'})

    monkeypatch.setattr(slackrepo, 'open_url', first)
    assert slackrepo.fetch_packages_txt('http://repo/')['gdal'] == [['proj']]
    assert calls == [{}]

    def not_modified(url, headers=None, **kwargs):
        calls.append(dict(headers))
        raise HTTPError(url, 304, 'Not Modified', {}, io.BytesIO())

    # A new worker process starts with an empty in-memory cache.
    monkeypatch.setattr(slackrepo, '_MEMO', {})
    monkeypatch.setattr(slackrepo, 'open_url', not_modified)
    assert slackrepo.fetch_packages_txt('http://repo/')['gdal'] == [['proj']]
    assert calls[1] == {'If-None-Match': '"v1"', 'If-Modified-Since': 'Tue, 27 Oct 2026 12:00:00 GMT'}


def test_fetch_reports_http_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(slackrepo, 'CACHE_DIR', str(tmp_path))
    monkeypatch.setattr(slackrepo, '_MEMO', {})

    def missing(url, headers=None, **kwargs):
        raise HTTPError(url, 404, 'Not Found', {}, io.BytesIO())

    monkeypatch.setattr(slackrepo, 'open_url', missing)
    with pytest.raises(AnsibleError, match='fetching http://repo/PACKAGES.TXT'):
        slackrepo.fetch_packages_txt('http://repo')
