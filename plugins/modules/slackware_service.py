#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Glitch Works, LLC
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

DOCUMENTATION = r'''
module: slackware_service
short_description: Manage Slackware services controlled by /etc/rc.d scripts
version_added: 0.1.0
description:
  - Starts, stops, restarts and reloads services through their C(/etc/rc.d/rc.<name>) script,
    and enables or disables them at boot by setting or clearing the script's execute bits.
  - Whether a service is running is determined from O(pattern) if given, otherwise from its
    PID file. A PID file only counts if the process it names is still alive, so a stale
    PID file left behind by a crash is treated as stopped.
  - Scripts are run through the interpreter on their C(#!) line, so a disabled
    (non-executable) script can still be stopped.
  - Making a script executable only starts the service at boot if C(rc.M), C(rc.inet2) or
    C(rc.local) calls it. Stock Slackware scripts are already called; services added from
    SlackBuilds usually need an C(rc.local) entry as well.
options:
  name:
    description: Service name; the script is C(/etc/rc.d/rc.<name>).
    type: str
    required: true
  state:
    description:
      - V(started) and V(stopped) act only when needed.
      - V(restarted) always restarts.
      - V(reloaded) reloads a running service and starts a stopped one. The script must
        support C(reload).
    type: str
    choices: [started, stopped, restarted, reloaded]
  enabled:
    description: Whether the script is executable, which is how Slackware decides what runs at boot.
    type: bool
  pidfile:
    description:
      - PID file used to tell whether the service is running.
      - Defaults to C(/var/run/<name>.pid). Set it for services that keep their PID file
        elsewhere, such as C(/var/run/cups/cupsd.pid).
    type: path
  pattern:
    description:
      - Treat the service as running if any process command line contains this string.
        Takes precedence over O(pidfile). Use it for services that write no PID file.
    type: str
  arguments:
    description: Extra arguments passed to the rc script after the action.
    type: str
    default: ''
    aliases: [args]
  sleep:
    description:
      - With O(state=restarted), run C(stop), wait this many seconds, then C(start),
        instead of calling the script's C(restart).
    type: int
extends_documentation_fragment:
  - ansible.builtin.action_common_attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: none
  platform:
    support: full
    platforms: linux
author:
  - Jonathan Chapman (@glitchwrks)
'''

EXAMPLES = r'''
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

- name: Restart a service that writes no PID file
  glitchwrks.slackware.slackware_service:
    name: vboxadd-service
    pattern: VBoxService
    state: restarted
'''

RETURN = r'''
name:
  description: Service name.
  returned: always
  type: str
script:
  description: Path to the rc script.
  returned: always
  type: str
enabled:
  description: Whether the script is executable after the task.
  returned: always
  type: bool
running:
  description: Whether the service was running before the task.
  returned: when O(state) is set
  type: bool
state:
  description: Requested state.
  returned: when O(state) is set
  type: str
actions:
  description: rc script actions run (or that would run, in check mode).
  returned: always
  type: list
  elements: str
'''

import os
import shlex
import stat
import tempfile
import time

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text

RC_DIR = '/etc/rc.d'
EXEC_BITS = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH


def pid_alive(pid):
    return os.path.exists('/proc/%d' % pid)


def running_from_pidfile(path):
    try:
        with open(path) as f:
            pid = int(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return False
    return pid > 0 and pid_alive(pid)


def running_from_pattern(pattern):
    me = os.getpid()
    for entry in os.listdir('/proc'):
        if not entry.isdigit() or int(entry) == me:
            continue
        try:
            with open('/proc/%s/cmdline' % entry, 'rb') as f:
                cmdline = to_text(f.read().replace(b'\0', b' '), errors='surrogate_or_replace')
        except OSError:
            continue
        if pattern in cmdline:
            return True
    return False


def interpreter(script):
    """Return the command prefix for running script, based on its #! line."""
    try:
        with open(script, 'rb') as f:
            first = to_text(f.readline(), errors='surrogate_or_replace').strip()
    except OSError:
        first = ''
    if first.startswith('#!'):
        return shlex.split(first[2:])
    return ['/bin/sh']


# Runs its arguments with stdin from /dev/null and stdout/stderr redirected to $OUT.
# The redirection replaces the pipes run_command attached, so a daemon the script
# starts inherits the file instead and run_command returns when the script exits.
REDIRECT_SH = 'exec "$@" </dev/null >"$OUT" 2>&1'


def run_script(module, script, action):
    """Run an rc script action.

    rc scripts often start daemons that inherit stdout and stderr. Capturing output
    through a pipe would then block until the daemon exits, so output goes to a temp
    file and only the script itself is waited on.
    """
    cmd = interpreter(script) + [script, action] + shlex.split(module.params['arguments'])
    fd, out_path = tempfile.mkstemp(prefix='slackware_service.', dir=module.tmpdir)
    os.close(fd)
    try:
        rc, dummy_out, err = module.run_command(['/bin/sh', '-c', REDIRECT_SH, 'sh'] + cmd,
                                                environ_update={'OUT': out_path})
        with open(out_path, 'rb') as f:
            output = to_text(f.read(), errors='surrogate_or_replace')
    finally:
        os.unlink(out_path)
    if rc != 0:
        module.fail_json(msg="%s %s failed (rc=%d)" % (script, action, rc), rc=rc,
                         output=output, stderr=err)
    return output


def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(type='str', required=True),
            state=dict(type='str', choices=['started', 'stopped', 'restarted', 'reloaded']),
            enabled=dict(type='bool'),
            pidfile=dict(type='path'),
            pattern=dict(type='str'),
            arguments=dict(type='str', default='', aliases=['args']),
            sleep=dict(type='int'),
        ),
        required_one_of=[['state', 'enabled']],
        supports_check_mode=True,
    )
    p = module.params
    name = p['name']
    script = os.path.join(RC_DIR, 'rc.%s' % name)
    if '/' in name or not os.path.isfile(script):
        module.fail_json(msg="no rc script for %s at %s" % (name, script))

    result = dict(name=name, script=script, changed=False, actions=[])

    # Boot-time enablement: the execute bits on the rc script.
    mode = stat.S_IMODE(os.stat(script).st_mode)
    if p['enabled'] is not None:
        want = (mode | EXEC_BITS) if p['enabled'] else (mode & ~EXEC_BITS)
        if want != mode:
            result['changed'] = True
            if not module.check_mode:
                os.chmod(script, want)
            mode = want
    result['enabled'] = bool(mode & stat.S_IXUSR)

    state = p['state']
    if state:
        if p['pattern']:
            running = running_from_pattern(p['pattern'])
        else:
            running = running_from_pidfile(p['pidfile'] or '/var/run/%s.pid' % name)
        result['running'] = running
        result['state'] = state

        if state == 'started':
            actions = [] if running else ['start']
        elif state == 'stopped':
            actions = ['stop'] if running else []
        elif state == 'reloaded':
            actions = ['reload'] if running else ['start']
        elif p['sleep']:
            actions = ['stop', 'start']
        else:
            actions = ['restart']

        result['actions'] = actions
        if actions:
            result['changed'] = True
            if not module.check_mode:
                output = []
                for i, action in enumerate(actions):
                    if i and p['sleep']:
                        time.sleep(p['sleep'])
                    output.append(run_script(module, script, action))
                result['output'] = ''.join(output)

    module.exit_json(**result)


if __name__ == '__main__':
    main()
