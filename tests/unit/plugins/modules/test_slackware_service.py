# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Glitch Works, LLC
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os

import pytest

from ansible_collections.glitchwrks.slackware.plugins.modules.slackware_service import (
    interpreter,
    running_from_pidfile,
)


def dead_pid():
    pid = 4194304  # above the default pid_max, so never a live process
    while os.path.exists('/proc/%d' % pid):
        pid += 1
    return pid


def test_pidfile_missing(tmp_path):
    assert running_from_pidfile(str(tmp_path / 'nope.pid')) is False


def test_pidfile_live_process(tmp_path):
    pidfile = tmp_path / 'svc.pid'
    pidfile.write_text('%d\n' % os.getpid())
    assert running_from_pidfile(str(pidfile)) is True


def test_pidfile_stale(tmp_path):
    pidfile = tmp_path / 'svc.pid'
    pidfile.write_text('%d\n' % dead_pid())
    assert running_from_pidfile(str(pidfile)) is False


@pytest.mark.parametrize('content', ['', 'garbage\n', '0\n', '-5\n'])
def test_pidfile_invalid(tmp_path, content):
    pidfile = tmp_path / 'svc.pid'
    pidfile.write_text(content)
    assert running_from_pidfile(str(pidfile)) is False


@pytest.mark.parametrize('first_line, expected', [
    ('#!/bin/bash\n', ['/bin/bash']),
    ('#!/bin/sh -e\n', ['/bin/sh', '-e']),
    ('#! /usr/bin/env bash\n', ['/usr/bin/env', 'bash']),
    ('# no shebang\n', ['/bin/sh']),
])
def test_interpreter(tmp_path, first_line, expected):
    script = tmp_path / 'rc.svc'
    script.write_text(first_line + 'echo hi\n')
    assert interpreter(str(script)) == expected


def test_interpreter_unreadable_script(tmp_path):
    assert interpreter(str(tmp_path / 'missing')) == ['/bin/sh']
