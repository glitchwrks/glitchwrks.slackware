# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Glitch Works, LLC
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import pytest

from ansible_collections.glitchwrks.slackware.plugins.action.slackpkg import _split_names


@pytest.mark.parametrize('value, expected', [
    (None, []),
    ('vagrant', ['vagrant']),
    ('a,b, c', ['a', 'b', 'c']),
    (['a', 'b,c', 'a'], ['a', 'b', 'c']),
    (['a,', ''], ['a']),
])
def test_split_names(value, expected):
    assert _split_names(value) == expected
